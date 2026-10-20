# Phase 9: Scale Calibration & Physical Measurement Verification Protocol

**Document ID**: `PROTO-SCALE-CALIB-09`  
**Effective Date**: 2026-10-20  
**Target Facility**: Main Campus Dining Hall (Kitchen A & Scullery)  
**Calibration Status**: **BLOCKED (PENDING ON-SITE PHYSICAL CALIBRATION)**  

---

## 1. Executive Summary & Purpose

Accurate food waste tracking and portion yield estimation depend on high-precision physical weight measurements. In Phase 7 and 8, data capture models were hardened to store cooked batch weight, unserved surplus weight, and customer plate waste as distinct, non-negative floating-point values.

However, **data models cannot guarantee physical truth if the scales in the kitchen and scullery are uncalibrated or improperly tared.** This protocol specifies the hardware inventory, certified reference standards, tare procedures, repeatability acceptance thresholds, and the on-site sign-off sheet required before staff commence weighing.

---

## 2. Hardware Inventory & Physical Deployment

Two dedicated industrial scales are assigned to Canteen Section A for the operational pilot:

| Device Identifier | Location | Device Type / Model | Operating Range | Precision / Resolution | Primary Operational Measurement |
|---|---|---|---|---|---|
| **`SCALE-KIT-01`** | Kitchen Hot Line Prep A | Mettler Toledo / OHAUS Defender Benchtop Scale | 0.02 kg – 30.00 kg | 0.01 kg (10 g) | Cooked batch weight & pan portion tare |
| **`SCALE-WST-01`** | Scullery / Dish Return Room | CAS DB-1H / Avery Berkel Heavy Platform Scale | 0.10 kg – 150.00 kg | 0.05 kg (50 g) | Customer plate waste bins & bulk surplus bins |

---

## 3. Reference Standards & Calibration Requirements

### 3.1 Traceable Test Weights
- **Reference Standard**: ISO/OIML Class M1 certified stainless steel cylindrical test weights:
  - 1.000 kg ($\pm 0.05\text{ g}$)
  - 5.000 kg ($\pm 0.25\text{ g}$)
- **Certification Source**: National Metrology Institute (NMI) / Certified Scale Inspection Laboratory.
- **Validity**: Calibrated within past 12 months.

### 3.2 Four-Point Physical Verification Procedure

Every operational scale must undergo and pass four physical checks prior to each pilot shift:

1. **Zero Point Check**:
   - Ensure scale pan is wiped clean, dry, and free of food debris.
   - Power on device; ensure digital readout stabilizes at exactly `0.00 kg`.
2. **Standard Pan Tare Check**:
   - Place empty standard stainless steel 1/1 Gastronorm (GN) hotel pan (standard depth 65mm, nominal weight 1.25 kg) on scale.
   - Depress **TARE** button.
   - Readout must display `0.00 kg` with the "NET" indicator illuminated.
   - Remove pan; readout must display `-1.25 kg` ($\pm 0.01\text{ kg}$).
3. **Reference Weight Accuracy Check**:
   - Place 5.000 kg Class M1 reference weight in center of weighing platform.
   - Readout must display between `4.99 kg` and `5.01 kg`.
4. **Repeatability Check**:
   - Place 5.000 kg weight on scale 5 consecutive times, removing it completely between trials.
   - Maximum allowable deviation between readings is $\le 0.02\text{ kg}$.

---

## 4. Strict Separation of Three Physical Measurement Streams

Kitchen staff and scullery stewards must adhere to strict physical stream separation. Under no circumstances may kitchen surplus be mixed with plate waste:

```
                                [ COOKING IN KITCHEN ]
                                          |
                                          v  [SCALE-KIT-01]
                                 (Cooked Batch Weight)
                                          |
                        +-----------------+-----------------+
                        |                                   |
                        v                                   v
             [ SERVED TO CUSTOMERS ]             [ UNSERVED IN KITCHEN ]
                        |                                   |
                        v                                   v
                 (Tray Scraped)                      (Pan Leftovers)
                        |                                   |
                        v  [SCALE-WST-01]                   v  [SCALE-KIT-01 / WST-01]
               [ PLATE WASTE STREAM ]              [ UNSERVED SURPLUS STREAM ]
           (Customer Returned Scraps)             (Clean, Edible Hotel Pan Food)
                        |                                   |
                        v                                   v
             Destination: Compost/Biofuel        Destination: Chilled Reuse/Donation
```

1. **Cooked Batch Weight (`prepared_weight_kg`)**:
   - Weighed immediately after cooking, before transfer to serving line steam table warmers.
   - Measured on `SCALE-KIT-01`.
2. **Unserved Kitchen Surplus (`unserved_surplus_weight_kg`)**:
   - Clean, edible food remaining in warmers after service closure (1:30 PM).
   - Food has never left the kitchen line and has never contacted customer trays.
   - Logged for chilled donation, staff consumption, or safe secondary preparation.
3. **Customer Plate Waste (`plate_waste_weight_kg`)**:
   - Post-consumer food scraps returned on dining trays to the dishwash scullery.
   - Inedible, contaminated scrap scraped directly into dedicated waste buckets.
   - Measured on `SCALE-WST-01` and sent to organic composting or biofuel.

---

## 5. Failed Check Protocol & Non-Conformity Handling

If any physical scale fails the calibration procedure:
1. **Immediate Quarantine**: Affix a physical red tag: *"OUT OF SERVICE - RECALIBRATION REQUIRED"*.
2. **No Data Entry Allowed**: Staff must NOT record visual estimates in place of digital scale readings.
3. **Backup Device Activation**: Switch to certified backup scale `SCALE-KIT-02` (kept in Kitchen Storage B).
4. **Audit Trail Logging**: Record the equipment issue in the daily shift report.

---

## 6. Physical Calibration Sign-Off Sheet (Template)

| Date | Device ID | Zero Check | Tare Check | 5.00 kg Ref Weight | Repeatability Range | Pass / Fail | Technician Signature |
|---|---|---|---|---|---|---|---|
| `[PENDING]` | `SCALE-KIT-01` | `0.00 kg` | `0.00 kg` | `[____] kg` | `[____] kg` | `[PENDING]` | ___________________ |
| `[PENDING]` | `SCALE-WST-01` | `0.00 kg` | `0.00 kg` | `[____] kg` | `[____] kg` | `[PENDING]` | ___________________ |

**Deployment Status**: **`BLOCKED (PENDING_PHYSICAL_CALIBRATION)`**. While data capture software is verified, live canteen staff data collection cannot commence until the calibration technician completes and signs the physical inspection record.
