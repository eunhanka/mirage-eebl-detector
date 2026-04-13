#include "ProposedIDMDetector.h"
#include <algorithm>
#include <sstream>

ProposedIDMDetector::ProposedIDMDetector() {}

void ProposedIDMDetector::reset() {
    history_.clear();
    eeblActive_.clear();
    eeblTriggerSpeed_.clear();
    eeblTriggerTime_.clear();
}

double ProposedIDMDetector::computeGap(double egoX, double senderX) const {
    return std::max(0.0, senderX - egoX - 5.0);  // 5.0 = vehicle length
}

bool ProposedIDMDetector::isAhead(double egoX, double senderX) const {
    return senderX > egoX;
}

double ProposedIDMDetector::computeTTC(double egoV, double senderV,
                                        double gap) const {
    double rel = egoV - senderV;
    if (rel <= 0.01 || gap <= 0) return -1.0;
    return gap / rel;
}

double ProposedIDMDetector::idmAccel(double egoV, double leaderV,
                                      double gap) const {
    gap = std::max(gap, 0.01);
    double dv = egoV - leaderV;
    double sqrtAB = std::sqrt(IDM_A * IDM_B);
    double sStar = IDM_S0 + egoV * IDM_T;
    if (dv > 0 && sqrtAB > 0)
        sStar += (egoV * dv) / (2.0 * sqrtAB);
    sStar = std::max(sStar, IDM_S0);

    double vRatio = (IDM_V0 > 0.01) ? (egoV / IDM_V0) : 0.0;
    double freeTerm = 1.0 - std::pow(vRatio, IDM_DELTA);
    double interact = std::pow(sStar / gap, 2);
    return std::max(IDM_A * (freeTerm - interact), -IDM_B * 2.0);
}

DetectionResult ProposedIDMDetector::evaluate(
    const BSMRecord& bsm, double egoX, double egoV)
{
    // Record BSM
    history_[bsm.senderId].push_back(bsm);
    if (history_[bsm.senderId].size() > 100)
        history_[bsm.senderId].pop_front();

    auto& hist = history_[bsm.senderId];
    int sid = bsm.senderId;

    double score = 0.0;
    std::vector<std::string> reasons;

    double gap = computeGap(egoX, bsm.x);
    bool ahead = isAhead(egoX, bsm.x);
    double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;

    // EEBL Gate: brake=1 AND ahead AND gap <= 300m
    bool isBrakingAhead = bsm.brake && ahead && gap <= EEBL_RANGE;
    bool wasEEBL = eeblActive_.count(sid) && eeblActive_[sid];
    bool eeblContext = isBrakingAhead || wasEEBL;

    // Stage 1: Context Assessment
    if (isBrakingAhead) {
        // Check 1a: TTC plausibility
        if (ttc < 0) {
            score += W_1A_TTC_RECEDE;
            reasons.push_back("TTC_RECEDING");
        } else if (ttc > TTC_WARN * 2.0) {
            score += W_1A_TTC_HIGH;
            reasons.push_back("TTC_HIGH");
        }

        // Check 1b: New sender (fewer than MIN_HIST records)
        if ((int)hist.size() <= MIN_HIST) {
            score += W_1B_NEW_SENDER;
            reasons.push_back("NEW_SENDER");
        }
    }

    // Stage 2: Deceleration Plausibility
    if (eeblContext && hist.size() >= 2) {
        const auto& prev = hist[hist.size() - 2];
        double dt = bsm.time - prev.time;
        if (dt > 0.001) {
            // Check 2a: Physical limit (|a| > g)
            if (std::abs(bsm.a) > MAX_DECEL) {
                score += W_2A_PHYS_LIMIT;
                reasons.push_back("PHYS_LIMIT");
            }

            // Check 2b: Cross-field consistency (Eq.5)
            double hatA = (bsm.v - prev.v) / dt;
            if (std::abs(hatA - bsm.a) > DECEL_TOL) {
                score += W_2B_CROSS_FIELD;
                reasons.push_back("CROSS_FIELD");
            }

            // Check 2c: Brake-speed mismatch
            if (bsm.brake && std::abs(hatA) < 0.5 * HARD_BRAKE) {
                score += W_2C_BRAKE_MISMATCH;
                reasons.push_back("BRAKE_MISMATCH");
            }
        }
    }

    // Stage 3: Behavioral Consistency
    if (eeblContext && (int)hist.size() >= MIN_HIST) {
        // Check 3a: Trajectory consistency (Eq.8, W=6 window)
        int inconsistent = 0, checked = 0;
        int startIdx = std::max(0, (int)hist.size() - TRAJ_WINDOW);
        for (int i = startIdx; i < (int)hist.size() - 1; i++) {
            double dtH = hist[i+1].time - hist[i].time;
            if (dtH <= 0.001) continue;
            checked++;
            double expDisp = hist[i].v * dtH + 0.5 * hist[i].a * dtH * dtH;
            double actDisp = std::abs(hist[i+1].x - hist[i].x);
            double tauX = std::max(1.0, 0.1 * std::max(hist[i].v, 0.0));
            if (std::abs(actDisp - expDisp) > tauX)
                inconsistent++;
        }
        if (checked > 0 && (double)inconsistent / checked > 0.4) {
            score += W_3A_TRAJ_CONS;
            reasons.push_back("TRAJ_INCONS");
        }

        // Check 3b: Post-EEBL speed (Eq.9)
        if (wasEEBL) {
            double eeblSpd = eeblTriggerSpeed_.count(sid) ?
                             eeblTriggerSpeed_[sid] : 0;
            double eeblTime = eeblTriggerTime_.count(sid) ?
                              eeblTriggerTime_[sid] : 0;
            int postN = 0, noDecel = 0;
            int recentStart = std::max(0, (int)hist.size() - 10);
            for (int i = recentStart + 1; i < (int)hist.size(); i++) {
                if (hist[i].time > eeblTime) {
                    postN++;
                    double dtH = hist[i].time - hist[i-1].time;
                    if (dtH > 0.001) {
                        double hatV = std::abs(hist[i].x - hist[i-1].x) / dtH;
                        if (hatV > 0.70 * eeblSpd)
                            noDecel++;
                    }
                }
            }
            if (postN >= 3 && (double)noDecel / std::max(postN, 1) > 0.5) {
                score += W_3B_POST_EEBL;
                reasons.push_back("POST_EEBL_NO_STOP");
            }
        }
    }

    // Check 3c: Position-speed mismatch (Eq.10)
    if (eeblContext && hist.size() >= 2) {
        const auto& prev = hist[hist.size() - 2];
        double dt = bsm.time - prev.time;
        if (dt > 0.001) {
            double hatV = std::abs(bsm.x - prev.x) / dt;
            if (std::abs(hatV - bsm.v) > SPEED_TOL) {
                score += W_3C_POS_SPD;
                reasons.push_back("POS_SPD_MISMATCH");
            }
        }
    }

    // Track EEBL activation
    if (isBrakingAhead && !wasEEBL) {
        eeblActive_[sid] = true;
        eeblTriggerSpeed_[sid] = bsm.v;
        eeblTriggerTime_[sid] = bsm.time;
    }

    // IDM Mitigation
    double mitA = 0.0;
    if (ahead && gap > 0)
        mitA = idmAccel(egoV, bsm.v, gap);

    // Build result
    std::stringstream ss;
    for (size_t i = 0; i < reasons.size(); i++) {
        if (i > 0) ss << ";";
        ss << reasons[i];
    }

    return {
        score >= THETA,
        std::min(score, 1.0),
        reasons.empty() ? "PASS" : ss.str(),
        ttc,
        mitA
    };
}
