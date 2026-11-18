"""Mock rejim: internet/API kalitsiz demo uchun tayyor ko'rik matnlari (STT natijasi o'rnida)."""

SCENARIOS = {
    "mother": {
        "severe": ("Og'ir holat (qizil)",
                   "Homiladorlik muddati o'ttiz ikki hafta. Qon bosimi bir yuz oltmish besh ga bir yuz o'n. "
                   "Gemoglobin oltmish sakkiz. Siydikda oqsil ikki plyus. Bemor kuchli bosh og'rig'i va ko'z oldi "
                   "qorong'ilashishiga shikoyat qiladi. Oyoqlarida shish bor. Homila harakati sustlashgan, "
                   "yurak urishi bir yuz qirq sakkiz. Xulosa: og'ir preeklampsiya shubhasi, og'ir anemiya. "
                   "Tavsiya: zudlik bilan perinatal markazga yotqizish. Keyingi ko'rik bir kundan keyin."),
        "moderate": ("O'rtacha xavf (sariq)",
                     "Homiladorlik yigirma olti hafta. Qon bosimi bir yuz qirq ikki ga to'qson. Gemoglobin to'qson "
                     "besh. Siydikda oqsil yo'q. Holsizlik va bosh aylanishiga shikoyat qiladi. Homila harakati "
                     "yaxshi. Vazni yetmish ikki kilo. Xulosa: o'rtacha anemiya, gestatsion gipertenziya. "
                     "Tavsiya: temir preparati, qon bosimini kunlik o'lchash. Keyingi ko'rik bir haftadan keyin."),
        "normal": ("Normal ko'rik (yashil)",
                   "Homiladorlik muddati yigirma hafta. Qon bosimi bir yuz o'n besh ga yetmish besh. Gemoglobin "
                   "bir yuz yigirma ikki. Siydikda oqsil topilmadi. Shikoyati yo'q. Homila harakati sezilmoqda, "
                   "yurak urishi bir yuz qirq. Shish yo'q. Xulosa: homiladorlik me'yorida kechmoqda. "
                   "Tavsiya: foliy kislota va vitaminlar. Keyingi ko'rik to'rt haftadan keyin."),
    },
    "child": {
        "severe": ("Og'ir holat (qizil)",
                   "Chaqaloq vazni uch ming ikki yuz gramm. Harorat o'ttiz sakkiz butun besh. Yomon emyapti, "
                   "terisi sarg'aygan. Nafas olishi qiyinlashgan. Xulosa: neonatal infeksiya shubhasi. "
                   "Tavsiya: zudlik bilan bolalar shifoxonasiga yo'llash. Keyingi ko'rik bir kundan keyin."),
        "normal": ("Normal ko'rik (yashil)",
                   "Bola vazni to'rt ming besh yuz gramm, bo'yi ellik besh santimetr, bosh aylanasi o'ttiz sakkiz butun besh, "
                   "ko'krak aylanasi o'ttiz yetti. Harorat o'ttiz olti butun "
                   "olti. Ko'krak suti bilan oziqlanadi, yaxshi emadi. Sariqlik yo'q. Xulosa: sog'lom, rivojlanishi "
                   "yoshiga mos. Tavsiya: ko'krak suti bilan boqishni davom ettirish. Keyingi ko'rik bir oydan keyin."),
    },
}


def transcript(kind, scenario):
    items = SCENARIOS[kind]
    return items.get(scenario, next(iter(items.values())))[1]


def choices(kind):
    return [(k, v[0]) for k, v in SCENARIOS[kind].items()]
