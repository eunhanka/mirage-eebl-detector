#ifndef PROPOSEDIDMDETECTOR_H_
#define PROPOSEDIDMDETECTOR_H_

#include <map>
#include <deque>
#include <vector>
#include <string>
#include <cmath>

// BSM structure (adapt to VASP's existing BSM struct)
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

class ProposedIDMDetector {
public:
    ProposedIDMDetector();
    ~ProposedIDMDetector() = default;

    DetectionResult evaluate(const BSMRecord& bsm,
                             double egoX, double egoV);
    void reset();

private:
    // Weights (Table 2)
    static constexpr double W_1A_TTC_HIGH    = 0.15;
    static constexpr double W_1A_TTC_RECEDE  = 0.35;
    static constexpr double W_1B_NEW_SENDER  = 0.20;
    static constexpr double W_2A_PHYS_LIMIT  = 0.20;
    static constexpr double W_2B_CROSS_FIELD = 0.15;
    static constexpr double W_2C_BRAKE_MISMATCH = 0.15;
    static constexpr double W_3A_TRAJ_CONS   = 0.20;
    static constexpr double W_3B_POST_EEBL   = 0.30;
    static constexpr double W_3C_POS_SPD     = 0.15;

    // Thresholds
    static constexpr double THETA       = 0.55;
    static constexpr double TTC_WARN    = 4.0;
    static constexpr double MAX_DECEL   = 9.81;
    static constexpr double HARD_BRAKE  = 3.92;  // 0.4g (SAE J2945)
    static constexpr double DECEL_TOL   = 1.5;
    static constexpr double SPEED_TOL   = 3.0;
    static constexpr int    MIN_HIST    = 3;
    static constexpr int    TRAJ_WINDOW = 6;
    static constexpr double EEBL_RANGE  = 300.0;

    // IDM Parameters
    static constexpr double IDM_V0    = 33.33;
    static constexpr double IDM_T     = 1.5;
    static constexpr double IDM_A     = 1.4;
    static constexpr double IDM_B     = 2.0;
    static constexpr double IDM_S0    = 2.0;
    static constexpr int    IDM_DELTA = 4;

    // State
    std::map<int, std::deque<BSMRecord>> history_;
    std::map<int, bool> eeblActive_;
    std::map<int, double> eeblTriggerSpeed_;
    std::map<int, double> eeblTriggerTime_;

    // Helpers
    double computeGap(double egoX, double senderX) const;
    bool isAhead(double egoX, double senderX) const;
    double computeTTC(double egoV, double senderV, double gap) const;
    double idmAccel(double egoV, double leaderV, double gap) const;
};

#endif
