import os, sys, time, json, requests
from datetime import date, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("TG_TOKEN")
JSONBIN_KEY = os.environ.get("JSONBIN_KEY")
JSONBIN_BIN = os.environ.get("JSONBIN_BIN")
API = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN}"
HEADERS = {"Content-Type":"application/json", "X-Master-Key": JSONBIN_KEY}

JN = {"inv":"Инвестиции","sofa":"На диван","spend":"Траты"}

def load():
    try:
        r = requests.get(API+"/latest", headers=HEADERS, timeout=15)
        if r.ok:
            rec = r.json().get("record", {})
            if isinstance(rec, dict) and "entries" in rec:
                return rec
    except Exception as e:
        print("Load error:", e)
    return {"entries":[]}

def save(data):
    try:
        requests.put(API, headers=HEADERS, json=data, timeout=15)
    except Exception as e:
        print("Save error:", e)

def fmt(n):
    return f"{n:,.2f} ₽".replace(",", " ")

def uid():
    return f"tg{int(time.time()*1000)}"

def calc_bal(entries):
    b = {"inv":0.0,"sofa":0.0,"spend":0.0}
    for e in sorted(entries, key=lambda x: x["date"]):
        if e["type"]=="income":
            b["inv"]+=e["amount"]*.33
            b["sofa"]+=e["amount"]*.10
            b["spend"]+=e["amount"]*.57
        else:
            b[e.get("fromJar","spend")] -= e["amount"]
    return b

async def start(u:Update, c:ContextTypes.DEFAULT_TYPE):
    txt = ("💰 *Финансовый трекер*\n\n"
           "/balance — баланс копилок\n"
           "/income 50000 ЗП — доход\n"
           "/spend 1500 Еда — трата из Трат\n"
           "/spend 1500 Еда|inv — из Инвестиций\n"
           "/invest 10000 Проект|spend — вложение\n"
           "/when 50000 — когда смогу потратить\n"
           "/when 50000|inv — из Инвестиций\n"
           "/list — последние 10 операций")
    await u.message.reply_text(txt, parse_mode="Markdown")

async def balance(u:Update, c:ContextTypes.DEFAULT_TYPE):
    data = load()
    b = calc_bal(data.get("entries",[]))
    total = b["inv"]+b["sofa"]+b["spend"]
    txt = (f"💰 *Баланс копилок:*\n\n"
           f"📈 Инвестиции: `{fmt(b['inv'])}`\n"
           f"🛋️ На диван: `{fmt(b['sofa'])}`\n"
           f"💸 Траты: `{fmt(b['spend'])}`\n\n"
           f"💎 *Всего:* `{fmt(total)}`")
    await u.message.reply_text(txt, parse_mode="Markdown")

async def income(u:Update, c:ContextTypes.DEFAULT_TYPE):
    args = c.args
    if not args:
        await u.message.reply_text("❌ Формат: /income 50000 ЗП"); return
    try: amount = float(args[0])
    except: await u.message.reply_text("❌ Сумма — число"); return
    note = " ".join(args[1:]) or "Доход"
    data = load()
    data.setdefault("entries",[]).append({
        "id":uid(),"type":"income","amount":amount,
        "date":date.today().isoformat(),"note":note
    })
    save(data)
    await u.message.reply_text(f"✅ Доход +{fmt(amount)} записан\n📝 {note}")

async def spend(u:Update, c:ContextTypes.DEFAULT_TYPE):
    args = c.args
    if not args:
        await u.message.reply_text("❌ Формат: /spend 1500 Еда|spend"); return
    try: amount = float(args[0])
    except: await u.message.reply_text("❌ Сумма — число"); return
    rest = " ".join(args[1:])
    note, jar = (rest.split("|",1)+["spend"])[:2]
    note = note.strip() or "Трата"
    jar = jar.strip()
    if jar not in ("inv","sofa","spend"): jar="spend"
    data = load()
    data.setdefault("entries",[]).append({
        "id":uid(),"type":"expense","amount":amount,"fromJar":jar,
        "date":date.today().isoformat(),"note":note
    })
    save(data)
    await u.message.reply_text(f"✅ Трата −{fmt(amount)} из «{JN[jar]}»\n📝 {note}")

async def invest(u:Update, c:ContextTypes.DEFAULT_TYPE):
    args = c.args
    if not args:
        await u.message.reply_text("❌ Формат: /invest 10000 Проект|spend"); return
    try: amount = float(args[0])
    except: await u.message.reply_text("❌ Сумма — число"); return
    rest = " ".join(args[1:])
    note, jar = (rest.split("|",1)+["spend"])[:2]
    note = note.strip() or "Вложение"
    jar = jar.strip()
    if jar not in ("inv","sofa","spend"): jar="spend"
    data = load()
    data.setdefault("entries",[]).append({
        "id":uid(),"type":"invest","amount":amount,"fromJar":jar,
        "date":date.today().isoformat(),"note":note
    })
    save(data)
    await u.message.reply_text(f"✅ Вложение −{fmt(amount)} из «{JN[jar]}»\n📝 {note}")

async def when_cmd(u:Update, c:ContextTypes.DEFAULT_TYPE):
    args = c.args
    if not args:
        await u.message.reply_text("❌ Формат: /when 50000 или /when 50000|inv"); return
    first = args[0]
    if "|" in first:
        amount_s, jar = first.split("|",1)
        try: amount = float(amount_s)
        except: await u.message.reply_text("❌ Сумма — число"); return
    else:
        jar = "spend"
        try: amount = float(first)
        except: await u.message.reply_text("❌ Сумма — число"); return
    if jar not in ("inv","sofa","spend"): jar="spend"

    data = load()
    entries = data.get("entries",[])
    today = date.today()
    past = [e for e in entries if e["date"]<=today.isoformat()]
    future = [e for e in entries if e["date"]>today.isoformat()]
    b = calc_bal(past)
    if b[jar]>=amount:
        await u.message.reply_text(f"🎉 Уже можешь! В «{JN[jar]}» сейчас {fmt(b[jar])}"); return

    by_date = {}
    for e in future:
        by_date.setdefault(e["date"],[]).append(e)
    d = today + timedelta(days=1)
    while d <= today + timedelta(days=730):
        ds = d.isoformat()
        for e in by_date.get(ds,[]):
            if e["type"]=="income":
                b["inv"]+=e["amount"]*.33;b["sofa"]+=e["amount"]*.10;b["spend"]+=e["amount"]*.57
            else:
                b[e.get("fromJar","spend")]-=e["amount"]
        if b[jar]>=amount:
            days = (d-today).days
            await u.message.reply_text(
                f"🎯 *{d.strftime('%d.%m.%Y')}* (через {days} дн.)\n"
                f"В «{JN[jar]}» будет {fmt(b[jar])}",
                parse_mode="Markdown"); return
        d += timedelta(days=1)
    await u.message.reply_text(f"⚠️ В ближайшие 2 года не получится. Добавь доходы.")

async def list_cmd(u:Update, c:ContextTypes.DEFAULT_TYPE):
    data = load()
    entries = sorted(data.get("entries",[]), key=lambda x:(x["date"],x["id"]), reverse=True)[:10]
    if not entries:
        await u.message.reply_text("📝 Пока нет операций"); return
    lines = ["📝 *Последние операции:*\n"]
    for e in entries:
        ico = "💰" if e["type"]=="income" else "💸" if e["type"]=="expense" else "📊"
        sign = "+" if e["type"]=="income" else "−"
        from_j = f" ({JN[e['fromJar']]})" if e.get("fromJar") else ""
        d = e["date"].split("-")
        date_s = f"{d[2]}.{d[1]}.{d[0]}"
        note = (e.get("note") or "").replace("_"," ").replace("*"," ")[:40]
        lines.append(f"{ico} {date_s} • {sign}{fmt(e['amount'])}{from_j}\n   _{note}_")
    await u.message.reply_text("\n\n".join(lines), parse_mode="Markdown")

async def unknown(u:Update, c:ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("❓ Неизвестная команда. Напиши /help")

def main():
    if not all([TOKEN, JSONBIN_KEY, JSONBIN_BIN]):
        print("❌ Не все переменные окружения заданы"); sys.exit(1)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("income", income))
    app.add_handler(CommandHandler("spend", spend))
    app.add_handler(CommandHandler("expense", spend))
    app.add_handler(CommandHandler("invest", invest))
    app.add_handler(CommandHandler("when", when_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("unknown", unknown))

    print("🤖 Бот запущен. Polling 4 минуты...")
    async def post_init(application):
        await application.bot.delete_webhook(drop_pending_updates=True)
    app.post_init = post_init

    app.run_polling(drop_pending_updates=True, close_loop=False)
    # Работаем 4 минуты, потом GitHub сам завершит (cron через 5 минут)
    time.sleep(240)
    print("✅ Сессия завершена")

if __name__ == "__main__":
    main()
