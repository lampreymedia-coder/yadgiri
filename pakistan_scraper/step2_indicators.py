"""
======================================================
 گام ۲: تعریف همه شاخص‌های Prosperity پاکستان
======================================================

سایت Data360 در بخش Prosperity این دسته‌ها رو داره:
  1. رشد اقتصادی (Economic Growth)
  2. درآمد و فقر (Income & Poverty)
  3. سلامت (Health)
  4. آموزش (Education)
  5. زیرساخت (Infrastructure)
  6. بازار کار (Labor Market)
  7. تجارت و سرمایه‌گذاری (Trade & Investment)
  8. محیط زیست (Environment)
"""

# ---------------------------------------------------
# دیکشنری کامل شاخص‌ها به تفکیک دسته
# ---------------------------------------------------
PROSPERITY_INDICATORS = {

    "📈 رشد اقتصادی": {
        "NY.GDP.MKTP.CD":       "GDP (دلار جاری)",
        "NY.GDP.MKTP.KD.ZG":    "نرخ رشد GDP (%)",
        "NY.GDP.PCAP.CD":       "GDP سرانه (دلار)",
        "NY.GDP.PCAP.KD.ZG":    "رشد GDP سرانه (%)",
        "NE.CON.PRVT.ZS":       "مصرف خانوار (% GDP)",
        "NE.GDI.TOTL.ZS":       "سرمایه‌گذاری کل (% GDP)",
    },

    "💰 درآمد و فقر": {
        "SI.POV.DDAY":          "فقر زیر ۲.۱۵$/روز (%)",
        "SI.POV.LMIC":          "فقر زیر ۳.۶۵$/روز (%)",
        "SI.POV.UMIC":          "فقر زیر ۶.۸۵$/روز (%)",
        "SI.POV.GINI":          "ضریب جینی (نابرابری درآمد)",
        "NY.GNP.PCAP.CD":       "درآمد ملی سرانه (GNI)",
        "SP.POP.TOTL":          "جمعیت کل",
    },

    "🏥 سلامت": {
        "SP.DYN.LE00.IN":       "امید به زندگی (سال)",
        "SH.DYN.MORT":          "مرگ‌ومیر زیر ۵ سال (در ۱۰۰۰)",
        "SH.STA.MMRT":          "مرگ‌ومیر مادران (در ۱۰۰,۰۰۰)",
        "SH.XPD.CHEX.GD.ZS":   "هزینه بهداشت (% GDP)",
        "SH.MED.PHYS.ZS":       "پزشک به ازای ۱۰۰۰ نفر",
        "SN.ITK.DEFC.ZS":       "سوءتغذیه (%)",
    },

    "📚 آموزش": {
        "SE.ADT.LITR.ZS":       "نرخ سواد بزرگسالان (%)",
        "SE.PRM.ENRR":          "ثبت‌نام ابتدایی (ناخالص %)",
        "SE.SEC.ENRR":          "ثبت‌نام متوسطه (ناخالص %)",
        "SE.TER.ENRR":          "ثبت‌نام دانشگاهی (ناخالص %)",
        "SE.XPD.TOTL.GD.ZS":   "هزینه آموزش (% GDP)",
    },

    "⚡ زیرساخت": {
        "EG.ELC.ACCS.ZS":       "دسترسی به برق (%)",
        "SH.H2O.BASW.ZS":       "دسترسی به آب سالم (%)",
        "SH.STA.BASS.ZS":       "دسترسی به بهداشت (%)",
        "IT.NET.USER.ZS":       "کاربران اینترنت (%)",
        "IT.CEL.SETS.P2":       "تلفن همراه (در ۱۰۰ نفر)",
        "IS.ROD.PAVE.ZS":       "جاده‌های آسفالت (%)",
    },

    "👷 بازار کار": {
        "SL.UEM.TOTL.ZS":       "نرخ بیکاری (%)",
        "SL.TLF.CACT.ZS":       "مشارکت نیروی کار (%)",
        "SL.TLF.CACT.FE.ZS":   "مشارکت زنان در بازار کار (%)",
        "SL.AGR.EMPL.ZS":       "اشتغال کشاورزی (%)",
        "SL.IND.EMPL.ZS":       "اشتغال صنعتی (%)",
    },

    "🌐 تجارت و مالیه": {
        "NE.EXP.GNFS.ZS":       "صادرات (% GDP)",
        "NE.IMP.GNFS.ZS":       "واردات (% GDP)",
        "BX.KLT.DINV.WD.GD.ZS":"سرمایه‌گذاری خارجی FDI (% GDP)",
        "BN.CAB.XOKA.GD.ZS":   "حساب جاری (% GDP)",
        "GC.DOD.TOTL.GD.ZS":   "بدهی دولتی (% GDP)",
        "FP.CPI.TOTL.ZG":      "تورم (%)",
    },

    "🌱 محیط زیست": {
        "EN.ATM.CO2E.PC":       "انتشار CO2 سرانه (تن)",
        "AG.LND.FRST.ZS":       "پوشش جنگلی (% زمین)",
        "ER.H2O.FWTL.ZS":      "برداشت آب شیرین (%)",
    },
}


def list_indicators():
    """نمایش همه شاخص‌ها"""
    total = 0
    for category, indicators in PROSPERITY_INDICATORS.items():
        print(f"\n{category}")
        print("-" * 50)
        for code, name in indicators.items():
            print(f"  {code:30s}  {name}")
            total += 1
    print(f"\n{'=' * 50}")
    print(f"  مجموع: {total} شاخص در {len(PROSPERITY_INDICATORS)} دسته")


if __name__ == "__main__":
    print("=" * 60)
    print("  لیست کامل شاخص‌های Prosperity پاکستان")
    print("=" * 60)
    list_indicators()
