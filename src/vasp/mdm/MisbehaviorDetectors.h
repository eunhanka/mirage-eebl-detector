#ifndef MISBEHAVIOR_DETECTORS_H_
#define MISBEHAVIOR_DETECTORS_H_

#include <map>
#include <deque>
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <sstream>
#include <numeric>

// --- Common Structures ---
struct BSMRecord {
    double time;
    int senderId;
    double x, v, a;
    bool brake;
};

struct DetectionResult {
    bool suspicious;
    double score;
    std::string reason;
    double ttc;
    double mitigatedAccel;
};

// --- Base Detector ---
class BaseDetector {
public:
    virtual ~BaseDetector() = default;
    virtual DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) = 0;
    virtual std::string name() const = 0;

    void reset() {
        history_.clear();
    }

protected:
    std::map<int, std::deque<BSMRecord>> history_;

    void record(const BSMRecord& bsm) {
        history_[bsm.senderId].push_back(bsm);
        if (history_[bsm.senderId].size() > 100)
            history_[bsm.senderId].pop_front();
    }

    static double computeGap(double egoX, double senderX) {
        return std::max(0.0, senderX - egoX - 5.0);
    }
    static double computeAbsGap(double egoX, double senderX) {
        return std::abs(senderX - egoX);
    }
    static bool isAhead(double egoX, double senderX) {
        return senderX > egoX;
    }
    static double computeTTC(double egoV, double senderV, double gap) {
        double rel = egoV - senderV;
        if (rel <= 0.01 || gap <= 0) return -1.0;
        return gap / rel;
    }

    DetectionResult makeResult(bool suspicious, double score,
                               const std::vector<std::string>& reasons,
                               double ttc, double mitA = 0.0) {
        std::stringstream ss;
        for (size_t i = 0; i < reasons.size(); i++) {
            if (i > 0) ss << ";";
            ss << reasons[i];
        }
        return {suspicious, std::min(score, 1.0),
                reasons.empty() ? "PASS" : ss.str(), ttc, mitA};
    }
};

// --- B0: Naive (No Detection) ---
class NaiveDetector : public BaseDetector {
public:
    std::string name() const override { return "B0_Naive"; }

    DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) override {
        record(bsm);
        double gap = computeGap(egoX, bsm.x);
        bool ahead = isAhead(egoX, bsm.x);
        double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;
        return makeResult(false, 0.0, {}, ttc);
    }
};

// --- B1: Threshold Detector ---
class ThresholdDetector : public BaseDetector {
public:
    std::string name() const override { return "B1_Threshold"; }

    DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) override {
        record(bsm);
        double score = 0.0;
        std::vector<std::string> reasons;

        if (bsm.v > MAX_SPEED || bsm.v < 0) {
            score += 0.40; reasons.push_back("SPD_RANGE");
        }
        if (std::abs(bsm.a) > MAX_ACCEL) {
            score += 0.40; reasons.push_back("ACC_RANGE");
        }
        if (computeAbsGap(egoX, bsm.x) > MAX_RANGE) {
            score += 0.30; reasons.push_back("COM_RANGE");
        }

        auto& hist = history_[bsm.senderId];
        if (hist.size() >= 2) {
            const auto& prev = hist[hist.size() - 2];
            double dt = bsm.time - prev.time;
            if (dt > 0.001) {
                double derivedA = (bsm.v - prev.v) / dt;
                if (bsm.brake && derivedA > -1.0) {
                    score += 0.30; reasons.push_back("BRAKE_NO_DECEL");
                }
                if (std::abs(bsm.a - derivedA) > 5.0) {
                    score += 0.25; reasons.push_back("ACC_MISMATCH");
                }
            }
        }

        double gap = computeGap(egoX, bsm.x);
        bool ahead = isAhead(egoX, bsm.x);
        double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;
        return makeResult(score >= THRESHOLD, score, reasons, ttc);
    }

private:
    static constexpr double MAX_SPEED  = 70.0;
    static constexpr double MAX_ACCEL  = 11.0;
    static constexpr double MAX_RANGE  = 300.0;
    static constexpr double THRESHOLD  = 0.4;
};

// --- B2: VCADS Detector ---
class VCADSDetector : public BaseDetector {
public:
    std::string name() const override { return "B2_VCADS"; }

    DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) override {
        record(bsm);
        double score = 0.0;
        std::vector<std::string> reasons;

        if (std::abs(bsm.a) > MAX_DECEL) {
            score += 0.30; reasons.push_back("FV_ACC");
        }
        if (bsm.v < -0.1) {
            score += 0.20; reasons.push_back("FV_NEG_SPD");
        }

        auto& hist = history_[bsm.senderId];
        if ((int)hist.size() >= 3) {
            int n = std::min(WINDOW, (int)hist.size() - 1);
            const auto& oldest = hist[hist.size() - 1 - n];
            const auto& newest = hist[hist.size() - 1];
            double dtW = newest.time - oldest.time;

            if (dtW > 0.01) {
                double sumSpeeds = 0, sumAccels = 0;
                int spdCount = 0, accCount = 0;
                for (int i = 0; i <= n; i++) {
                    sumSpeeds += hist[hist.size() - 1 - i].v;
                    spdCount++;
                }
                for (int i = 0; i < n; i++) {
                    sumAccels += hist[hist.size() - 1 - i].a;
                    accCount++;
                }

                double smoothDA = (newest.v - oldest.v) / dtW;
                double avgRA = (accCount > 0) ? sumAccels / accCount : 0;
                if (std::abs(avgRA - smoothDA) > ACCEL_TOL) {
                    score += 0.25; reasons.push_back("CV_ACC");
                }

                double totalDist = std::abs(newest.x - oldest.x);
                double avgSpeed = (spdCount > 0) ? sumSpeeds / spdCount : 0;
                double expDist = avgSpeed * dtW;
                if (std::abs(totalDist - expDist) > POS_TOL + SPEED_TOL * dtW) {
                    score += 0.25; reasons.push_back("CV_POS");
                }

                double posSpeed = totalDist / dtW;
                if (std::abs(posSpeed - avgSpeed) > SPEED_TOL) {
                    score += 0.20; reasons.push_back("CV_SPD");
                }
            }
        }

        double gap = computeGap(egoX, bsm.x);
        bool ahead = isAhead(egoX, bsm.x);
        double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;
        return makeResult(score >= THRESHOLD, score, reasons, ttc);
    }

private:
    static constexpr double ACCEL_TOL = 3.5;
    static constexpr double SPEED_TOL = 5.0;
    static constexpr double POS_TOL   = 15.0;
    static constexpr double MAX_DECEL = 9.81;
    static constexpr double THRESHOLD = 0.45;
    static constexpr int    WINDOW    = 5;
};

// --- B3: F2MD Detector ---
class F2MDDetector : public BaseDetector {
public:
    std::string name() const override { return "B3_F2MD"; }

    DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) override {
        record(bsm);
        int failed = 0, total = 0;
        std::vector<std::string> reasons;

        total++;
        if (computeAbsGap(egoX, bsm.x) > MAX_RANGE) {
            failed++; reasons.push_back("RNG");
        }

        total++;
        if (bsm.v > MAX_SPEED || bsm.v < 0) {
            failed++; reasons.push_back("SPD");
        }

        auto& hist = history_[bsm.senderId];
        if (hist.size() >= 2) {
            const auto& prev = hist[hist.size() - 2];
            double dt = bsm.time - prev.time;
            if (dt > 0.001) {
                double posDist = std::abs(bsm.x - prev.x);

                total++;
                if (posDist > POS_JUMP_RATE * dt) {
                    failed++; reasons.push_back("POS_JUMP");
                }

                total++;
                double derivedSpd = posDist / dt;
                double avgSpd = (prev.v + bsm.v) / 2.0;
                if (std::abs(derivedSpd - avgSpd) > SPEED_CONS_TOL) {
                    failed++; reasons.push_back("POS_SPD");
                }

                total++;
                if (dt < MIN_INTERVAL || dt > MAX_INTERVAL) {
                    failed++; reasons.push_back("FREQ");
                }

                total++;
                double derivedA = (bsm.v - prev.v) / dt;
                if (std::abs(bsm.a - derivedA) > ACCEL_CONS_TOL) {
                    failed++; reasons.push_back("ACC_CONS");
                }
                }
        }

        double score = (total > 0) ? (double)failed / total : 0.0;

        double gap = computeGap(egoX, bsm.x);
        bool ahead = isAhead(egoX, bsm.x);
        double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;
        return makeResult(score >= THRESHOLD, score, reasons, ttc);
    }

private:
    static constexpr double MAX_RANGE      = 300.0;
    static constexpr double MAX_SPEED      = 70.0;
    static constexpr double POS_JUMP_RATE  = 50.0;
    static constexpr double SPEED_CONS_TOL = 3.0;
    static constexpr double ACCEL_CONS_TOL = 3.0;
    static constexpr double MIN_INTERVAL   = 0.05;
    static constexpr double MAX_INTERVAL   = 2.0;
    static constexpr double THRESHOLD      = 0.35;
};

// --- Proposed: IDM-based EEBL Detector ---
class ProposedIDMDetector : public BaseDetector {
public:
    std::string name() const override { return "P_Proposed"; }

    DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) override {
        record(bsm);
        auto& hist = history_[bsm.senderId];
        int sid = bsm.senderId;

        double score = 0.0;
        std::vector<std::string> reasons;

        double gap = computeGap(egoX, bsm.x);
        double absGap = computeAbsGap(egoX, bsm.x);
        bool ahead = isAhead(egoX, bsm.x);
        double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;

        // EEBL Gate: timeout and consecutive-brake requirement
        // Require >= 2 consecutive brake BSMs to open gate (prevents
        // single transient eventHardBraking from normal vehicles)
        bool isBrakingNearby = false;
        if (bsm.brake && absGap <= EEBL_RANGE) {
            int consecBrake = 0;
            for (int i = (int)hist.size() - 1; i >= std::max(0, (int)hist.size() - 3); i--) {
                if (hist[i].brake) consecBrake++;
                else break;
            }
            isBrakingNearby = (consecBrake >= 2);
        }

        // Expire EEBL state after timeout
        bool wasEEBL = false;
        if (eeblActive_.count(sid) && eeblActive_[sid]) {
            double elapsed = bsm.time - eeblTriggerTime_[sid];
            if (elapsed > EEBL_TIMEOUT) {
                eeblActive_[sid] = false;  // expired
            } else {
                wasEEBL = true;
            }
        }

        bool eeblContext = isBrakingNearby || wasEEBL;

        // Stage 1: Context Assessment
        if (isBrakingNearby) {
            if (!ahead) {
                score += W_1A_TTC_RECEDE; reasons.push_back("TTC_RECEDING");
            } else if (ttc < 0) {
                score += W_1A_TTC_RECEDE; reasons.push_back("TTC_RECEDING");
            } else if (ttc > TTC_WARN * 2.0) {
                score += W_1A_TTC_HIGH; reasons.push_back("TTC_HIGH");
            }
            if ((int)hist.size() <= MIN_HIST) {
                score += W_1B_NEW_SENDER; reasons.push_back("NEW_SENDER");
            }
        }

        // Stage 2: Deceleration Plausibility
        if (eeblContext && hist.size() >= 2) {
            const auto& prev = hist[hist.size() - 2];
            double dt = bsm.time - prev.time;
            if (dt > 0.001) {
                if (std::abs(bsm.a) > MAX_DECEL) {
                    score += W_2A_PHYS_LIMIT; reasons.push_back("PHYS_LIMIT");
                }
                double hatA = (bsm.v - prev.v) / dt;
                if (std::abs(hatA - bsm.a) > DECEL_TOL) {
                    score += W_2B_CROSS_FIELD; reasons.push_back("CROSS_FIELD");
                }
                if (bsm.brake && std::abs(hatA) < 0.5 * HARD_BRAKE) {
                    score += W_2C_BRAKE_MISMATCH; reasons.push_back("BRAKE_MISMATCH");
                }
            }
        }

        // Stage 3: Behavioral Consistency
        if (eeblContext && (int)hist.size() >= MIN_HIST) {
            // 3a: Trajectory consistency (relaxed tolerance for SUMO)
            int inconsistent = 0, checked = 0;
            int startIdx = std::max(0, (int)hist.size() - TRAJ_WINDOW);
            for (int i = startIdx; i < (int)hist.size() - 1; i++) {
                double dtH = hist[i+1].time - hist[i].time;
                if (dtH <= 0.001) continue;
                checked++;
                double expDisp = hist[i].v * dtH + 0.5 * hist[i].a * dtH * dtH;
                double actDisp = std::abs(hist[i+1].x - hist[i].x);
                // Wider tolerance for SUMO: base 3.0m + 20% of speed
                double tauX = std::max(3.0, 0.20 * std::max(hist[i].v, 0.0));
                if (std::abs(actDisp - expDisp) > tauX) inconsistent++;
            }
            if (checked > 0 && (double)inconsistent / checked > 0.5) {
                score += W_3A_TRAJ_CONS; reasons.push_back("TRAJ_INCONS");
            }

            // 3b: Post-EEBL speed (only if EEBL was recent)
            if (wasEEBL) {
                double eeblSpd = eeblTriggerSpeed_.count(sid) ? eeblTriggerSpeed_[sid] : 0;
                double eeblTime = eeblTriggerTime_.count(sid) ? eeblTriggerTime_[sid] : 0;
                int postN = 0, noDecel = 0;
                int recentStart = std::max(0, (int)hist.size() - 10);
                for (int i = recentStart + 1; i < (int)hist.size(); i++) {
                    if (hist[i].time > eeblTime) {
                        postN++;
                        double dtH = hist[i].time - hist[i-1].time;
                        if (dtH > 0.001) {
                            double hatV = std::abs(hist[i].x - hist[i-1].x) / dtH;
                            if (hatV > 0.80 * eeblSpd) noDecel++;
                        }
                    }
                }
                if (postN >= 3 && (double)noDecel / std::max(postN, 1) > 0.6) {
                    score += W_3B_POST_EEBL; reasons.push_back("POST_EEBL_NO_STOP");
                }
            }
        }

        // 3c: Position-speed mismatch (wider tolerance)
        if (eeblContext && hist.size() >= 2) {
            const auto& prev = hist[hist.size() - 2];
            double dt = bsm.time - prev.time;
            if (dt > 0.001) {
                double hatV = std::abs(bsm.x - prev.x) / dt;
                if (std::abs(hatV - bsm.v) > SPEED_TOL) {
                    score += W_3C_POS_SPD; reasons.push_back("POS_SPD_MISMATCH");
                }
            }
        }

        // Stage 4: Frozen Position Detection
        // If sender position doesn't change over N BSMs but claims speed > 0
        if (hist.size() >= 4) {
            int frozen = 0, frozenChecked = 0;
            int startIdx = std::max(0, (int)hist.size() - 5);
            for (int i = startIdx; i < (int)hist.size() - 1; i++) {
                frozenChecked++;
                double posDiff = std::abs(hist[i+1].x - hist[i].x);
                if (posDiff < 0.01) frozen++;
            }
            if (frozenChecked >= 3 && (double)frozen / frozenChecked > 0.8) {
                // Position frozen -- check if speed or accel suggest movement
                double avgV = 0;
                for (int i = startIdx; i < (int)hist.size(); i++) avgV += hist[i].v;
                avgV /= (hist.size() - startIdx);
                if (avgV > 0.5 || bsm.brake) {
                    score += W_4_FROZEN_POS; reasons.push_back("FROZEN_POS");
                }
            }
        }

        // Track EEBL
        if (isBrakingNearby && !wasEEBL) {
            eeblActive_[sid] = true;
            eeblTriggerSpeed_[sid] = bsm.v;
            eeblTriggerTime_[sid] = bsm.time;
        }

        // IDM Mitigation
        double mitA = 0.0;
        if (ahead && gap > 0) mitA = idmAccel(egoV, bsm.v, gap);

        return makeResult(score >= THETA, score, reasons, ttc, mitA);
    }

protected:
    double idmAccel(double egoV, double leaderV, double gap) const {
        gap = std::max(gap, 0.01);
        double dv = egoV - leaderV;
        double sqrtAB = std::sqrt(IDM_A * IDM_B);
        double sStar = IDM_S0 + egoV * IDM_T;
        if (dv > 0 && sqrtAB > 0) sStar += (egoV * dv) / (2.0 * sqrtAB);
        sStar = std::max(sStar, IDM_S0);
        double vRatio = (IDM_V0 > 0.01) ? (egoV / IDM_V0) : 0.0;
        double freeTerm = 1.0 - std::pow(vRatio, IDM_DELTA);
        double interact = std::pow(sStar / gap, 2);
        return std::max(IDM_A * (freeTerm - interact), -IDM_B * 2.0);
    }

    // Detection check weights
    static constexpr double W_1A_TTC_HIGH = 0.15, W_1A_TTC_RECEDE = 0.35;
    static constexpr double W_1B_NEW_SENDER = 0.20;
    static constexpr double W_2A_PHYS_LIMIT = 0.20, W_2B_CROSS_FIELD = 0.15;
    static constexpr double W_2C_BRAKE_MISMATCH = 0.15;
    static constexpr double W_3A_TRAJ_CONS = 0.20, W_3B_POST_EEBL = 0.30;
    static constexpr double W_3C_POS_SPD = 0.15;
    static constexpr double W_4_FROZEN_POS = 0.60;  // New: catches A2
    static constexpr double THETA = 0.55, TTC_WARN = 4.0;
    static constexpr double MAX_DECEL = 9.81, HARD_BRAKE = 3.92;
    static constexpr double DECEL_TOL = 2.5;
    static constexpr double SPEED_TOL = 6.0;   // widened for SUMO
    static constexpr int MIN_HIST = 3, TRAJ_WINDOW = 6;
    static constexpr double EEBL_RANGE = 300.0;
    static constexpr double EEBL_TIMEOUT = 5.0;  // New: gate expires after 5s
    static constexpr double IDM_V0 = 33.33, IDM_T = 1.5, IDM_A = 1.4;
    static constexpr double IDM_B = 2.0, IDM_S0 = 2.0;
    static constexpr int IDM_DELTA = 4;

    std::map<int, bool> eeblActive_;
    std::map<int, double> eeblTriggerSpeed_;
    std::map<int, double> eeblTriggerTime_;
};

// --- Ablation: Proposed without EEBL Gate ---
class ProposedNoGateDetector : public ProposedIDMDetector {
public:
    std::string name() const override { return "P_NoGate"; }
    DetectionResult evaluate(const BSMRecord& bsm, double egoX, double egoV) override {
        record(bsm);
        auto& hist = history_[bsm.senderId];
        double score = 0.0;
        std::vector<std::string> reasons;
        double gap = computeGap(egoX, bsm.x);
        double absGap = computeAbsGap(egoX, bsm.x);
        bool ahead = isAhead(egoX, bsm.x);
        double ttc = ahead ? computeTTC(egoV, bsm.v, gap) : -1.0;
        bool runChecks = bsm.brake; /* NO gate: any brake=true */
        if (runChecks) {
            if (!ahead || ttc < 0) { score += W_1A_TTC_RECEDE; reasons.push_back("TTC_RECEDING"); }
            else if (ttc > TTC_WARN * 2.0) { score += W_1A_TTC_HIGH; reasons.push_back("TTC_HIGH"); }
            if ((int)hist.size() <= MIN_HIST) { score += W_1B_NEW_SENDER; reasons.push_back("NEW_SENDER"); }
        }
        if (runChecks && hist.size() >= 2) {
            const auto& prev = hist[hist.size()-2];
            double dt = bsm.time - prev.time;
            if (dt > 0.001) {
                if (std::abs(bsm.a) > MAX_DECEL) { score += W_2A_PHYS_LIMIT; reasons.push_back("PHYS_LIMIT"); }
                double hatA = (bsm.v - prev.v) / dt;
                if (std::abs(hatA - bsm.a) > DECEL_TOL) { score += W_2B_CROSS_FIELD; reasons.push_back("CROSS_FIELD"); }
                if (bsm.brake && std::abs(hatA) < 0.5*HARD_BRAKE) { score += W_2C_BRAKE_MISMATCH; reasons.push_back("BRAKE_MISMATCH"); }
            }
        }
        if (runChecks && (int)hist.size() >= MIN_HIST) {
            int incons=0, checked=0, startIdx=std::max(0,(int)hist.size()-TRAJ_WINDOW);
            for (int i=startIdx; i<(int)hist.size()-1; i++) {
                double dtH=hist[i+1].time-hist[i].time; if(dtH<=0.001) continue; checked++;
                double expD=hist[i].v*dtH+0.5*hist[i].a*dtH*dtH;
                double actD=std::abs(hist[i+1].x-hist[i].x);
                double tauX=std::max(3.0,0.20*std::max(hist[i].v,0.0));
                if(std::abs(actD-expD)>tauX) incons++;
            }
            if(checked>0 && (double)incons/checked>0.5) { score+=W_3A_TRAJ_CONS; reasons.push_back("TRAJ_INCONS"); }
            if(hist.size()>=2) {
                const auto& prev=hist[hist.size()-2]; double dt=bsm.time-prev.time;
                if(dt>0.001) { double hatV=std::abs(bsm.x-prev.x)/dt;
                    if(std::abs(hatV-bsm.v)>SPEED_TOL) { score+=W_3C_POS_SPD; reasons.push_back("POS_SPD_MISMATCH"); }
                }
            }
        }
        if(hist.size()>=4) {
            int frozen=0,fc=0,si=std::max(0,(int)hist.size()-5);
            for(int i=si;i<(int)hist.size()-1;i++){fc++;if(std::abs(hist[i+1].x-hist[i].x)<0.01)frozen++;}
            if(fc>=3&&(double)frozen/fc>0.8){double av=0;for(int i=si;i<(int)hist.size();i++)av+=hist[i].v;av/=(hist.size()-si);
                if(av>0.5||bsm.brake){score+=W_4_FROZEN_POS;reasons.push_back("FROZEN_POS");}}
        }
        double mitA=0.0; if(ahead&&gap>0) mitA=idmAccel(egoV,bsm.v,gap);
        return makeResult(score>=THETA, score, reasons, ttc, mitA);
    }
};

// --- Factory Function ---
inline BaseDetector* createDetector(int type) {
    switch (type) {
        case 0: return new NaiveDetector();
        case 1: return new ThresholdDetector();
        case 2: return new VCADSDetector();
        case 3: return new F2MDDetector();
        case 4: return new ProposedIDMDetector();
        case 5: return new ProposedNoGateDetector();
        default: return new ProposedIDMDetector();
    }
}

#endif
