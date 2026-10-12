"""Scaled adult inpatient capacity for the synthetic hospital only.

SNUH main campus, 2025-12-31: 1,130 general beds and 106 adult ICU beds.
Special isolation beds, paediatric beds and NICU are outside this demo scope.
The reference supports the bed mix, not the synthetic case mix or staffing.
"""

WARD_BEDS = 128
ICU_UNITS = (("SICU", 8), ("CCU", 4))
BED_REFERENCE = {
    "name": "서울대학교병원 본원 현황 및 통계",
    "url": "https://www.snuh.org/content/M005004002.do",
    "as_of": "2025-12-31",
    "general_beds": 1130,
    "adult_icu_beds": 106,
    "scope": "일반병상과 성인 ICU만 비교; 특수·소아·신생아 병상 제외",
}
