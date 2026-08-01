import discord
from discord.ext import commands, tasks
import yfinance as yf
import pandas_ta as ta
import math
import asyncio
import time
import datetime
import os
from google import genai
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# --- 24시간 생존 웹서버 ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("🔥 Quant Bot is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# --- 보안 키 불러오기 ---
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

api_semaphore = asyncio.Semaphore(5)
data_cache, user_portfolios, user_alerts, savings_tracker, knowledge_base = {}, {}, {}, {}, {'verified_facts': []}
CACHE_TTL = 600  

KST = datetime.timezone(datetime.timedelta(hours=9))
morning_time = datetime.time(hour=8, minute=0, tzinfo=KST)
morning_channel_id = None

@bot.event
async def on_ready():
    print(f'🔥 V11.1 접속 완료: {bot.user.name}')
    if not memory_cleanup_task.is_running(): memory_cleanup_task.start()
    if not background_learning_engine.is_running(): background_learning_engine.start()
    if not sniper_monitor.is_running(): sniper_monitor.start()
    if not morning_report.is_running(): morning_report.start()

def sync_ask_ai(prompt, system_role, fast=False):
    strict_prompt = f"{system_role}\n\n[출력 원칙]\n1. 마크다운 표와 글머리 기호 사용.\n2. 모호한 추측 금지.\n\n{prompt}"
    try:
        res = client.models.generate_content(model='gemini-1.5-flash' if fast else 'gemini-1.5-pro', contents=strict_prompt)
        return res.text if res.text else "🚨 응답 없음"
    except Exception as e: return f"🚨 오류: {e}"

async def ask_ai_async(prompt, system_role, fast=False):
    async with api_semaphore:
        try: return await asyncio.wait_for(asyncio.to_thread(sync_ask_ai, prompt, system_role, fast), timeout=15.0)
        except: return "🚨 [타임아웃] 연산 초과."

async def fetch_stock_async(ticker, period="5d"):
    curr = time.time()
    if ticker in data_cache and (curr - data_cache[ticker]['timestamp']) < CACHE_TTL: return data_cache[ticker]['data']
    async with api_semaphore:
        try:
            hist = await asyncio.to_thread(yf.Ticker(ticker).history, period=period)
            if not hist.empty: data_cache[ticker] = {'data': hist, 'timestamp': curr}
            return hist
        except: return None

@tasks.loop(minutes=15.0)
async def memory_cleanup_task():
    curr = time.time()
    for k in [k for k, v in data_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del data_cache[k]

@tasks.loop(minutes=10.0)
async def background_learning_engine():
    for t in ["AAPL", "NVDA", "TSLA"]:
        try:
            news = await asyncio.to_thread(lambda: yf.Ticker(t).news)
            if not news: continue
            title = news[0].get('title', '')
            if "PASS" in await ask_ai_async(f"뉴스: {title}. 팩트면 PASS, 찌라시면 REJECT.", "팩트체크", fast=True):
                fact = f"[{t}] {title}"
                if fact not in knowledge_base['verified_facts']:
                    knowledge_base['verified_facts'].append(fact)
                    if len(knowledge_base['verified_facts']) > 20: knowledge_base['verified_facts'].pop(0)
        except: pass

@tasks.loop(minutes=5.0)
async def sniper_monitor():
    for uid, alerts in list(user_alerts.items()):
        for al in alerts[:]:
            try:
                hist = await fetch_stock_async(al['ticker'], "1d")
                if hist is None: continue
                curr_p = hist['Close'].iloc[-1]
                tg = al['target_price']
                if abs(curr_p - tg) / tg <= 0.01 or (curr_p <= tg if al['is_buy'] else curr_p >= tg):
                    ch = bot.get_channel(al['channel_id'])
                    usr = await bot.fetch_user(uid)
                    if ch and usr: await ch.send(f"🚨 {usr.mention}님! **{al['ticker']}** 목표가 ${tg:.2f} 도달! (현재: ${curr_p:.2f})")
                    alerts.remove(al)
            except: pass

@tasks.loop(time=morning_time)
async def morning_report():
    if not morning_channel_id: return
    ch = bot.get_channel(morning_channel_id)
    if not ch: return
    await ch.send("🌅 **모닝 브리핑 준비 중...**")
    try:
        spy, vix = await fetch_stock_async("SPY", "5d"), await fetch_stock_async("^VIX", "1d")
        spy_c = ((spy['Close'].iloc[-1] - spy['Close'].iloc[-2]) / spy['Close'].iloc[-2]) * 100 if spy is not None else 0
        vix_v = vix['Close'].iloc[-1] if vix is not None else 20
        port_str = "등록된 종목 없음."
        if user_portfolios:
            uid = list(user_portfolios.keys())[0]
            port_data = [f"- **{t}**: {((await fetch_stock_async(t, '5d'))['Close'].iloc[-1] / (await fetch_stock_async(t, '5d'))['Close'].iloc[-2] - 1)*100:+.2f}%" for t in user_portfolios[uid] if (await fetch_stock_async(t, '5d')) is not None]
            if port_data: port_str = "\n".join(port_data)
        ans = await ask_ai_async(f"S&P: {spy_c:+.2f}%, VIX: {vix_v:.1f}\n내서재:\n{port_str}\n날씨 비유로 시장 브리핑 및 대응 전략 짜줘.", "수석 전략가")
        await ch.send(embed=discord.Embed(title="🌅 굿모닝 마켓 브리핑", description=ans, color=0xFFD700))
    except: await ch.send("🚨 모닝 브리핑 실패")

class QuantOrderModal(discord.ui.Modal, title='🛒 퀀트 토스 소수점 주문'):
    ticker = discord.ui.TextInput(label='종목', placeholder='NVDA')
    budget = discord.ui.TextInput(label='투입 원화', placeholder='5000')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        t, bdg = self.ticker.value.upper(), float(self.budget.value.replace(',', ''))
        hist, vix_h, krw_h = await fetch_stock_async(t, "1d"), await fetch_stock_async("^VIX", "1d"), await fetch_stock_async("USDKRW=X", "1d")
        krw_r = krw_h['Close'].iloc[-1] if krw_h is not None else 1400
        prc = hist['Close'].iloc[-1] * krw_r if hist is not None else 0
        vix = vix_h['Close'].iloc[-1] if vix_h is not None else 20
        inv = bdg * (1 - (70 if vix > 30 else (40 if vix > 20 else 10))/100)
        ans = await ask_ai_async(f"종목:{t}({prc:,.0f}원) 총예산:{bdg:,.0f}원 VIX:{vix:.1f}. 토스 소수점 매매로 {inv:,.0f}원만 사고 대기하는 플랜 짜줘.", "수석 트레이더")
        await interaction.followup.send(embed=discord.Embed(title=f"🛒 {t} 퀀트 주문서", description=ans, color=0x0050FF))

class ReportModal(discord.ui.Modal, title='👑 360도 팩트체크'):
    ticker = discord.ui.TextInput(label='종목', placeholder='AAPL')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        t = self.ticker.value.upper()
        price = (await fetch_stock_async(t, "6mo"))['Close'].iloc[-1] if await fetch_stock_async(t, "6mo") is not None else 0
        ans = await ask_ai_async(f"종목:{t} 현재가:${price:.2f}. 어닝 리스크, 지지/저항선, 매매 결론 팩트폭격해.", "애널리스트")
        await interaction.followup.send(embed=discord.Embed(title=f"📊 {t} 리포트", description=ans, color=0x0050FF))

class SniperModal(discord.ui.Modal, title='🎯 스나이퍼 설정'):
    ticker = discord.ui.TextInput(label='종목', placeholder='AAPL')
    target = discord.ui.TextInput(label='목표가($)', placeholder='150')
    action = discord.ui.TextInput(label='매수/매도', placeholder='매수')
    async def on_submit(self, interaction: discord.Interaction):
        t, tg = self.ticker.value.upper(), float(self.target.value)
        if interaction.user.id not in user_alerts: user_alerts[interaction.user.id] = []
        user_alerts[interaction.user.id].append({'ticker': t, 'target_price': tg, 'channel_id': interaction.channel.id, 'is_buy': "매수" in self.action.value})
        await interaction.response.send_message(f"✅ **{t}** ${tg:.2f} 도달 시 핑 울림!", ephemeral=True)

class HabitJournalModal(discord.ui.Modal, title='🔥 절약 & 일지'):
    saved = discord.ui.TextInput(label='오늘 아낀 돈', placeholder='3000')
    trade = discord.ui.TextInput(label='오늘 매매 내역', placeholder='없음', required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = interaction.user.id
        amt = float(self.saved.value.replace(',', '')) if self.saved.value else 0
        savings_tracker[uid] = savings_tracker.get(uid, 0) + amt
        ans = await ask_ai_async(f"절약:{amt}원 누적:{savings_tracker[uid]}원. 매매:'{self.trade.value}'. 뇌동매매 팩폭 및 칭찬해.", "멘탈트레이너", fast=True)
        await interaction.followup.send(embed=discord.Embed(title="🔥 피드백", description=ans, color=0xFFD700))

class LibraryModal(discord.ui.Modal, title='📚 서재 관리'):
    action = discord.ui.TextInput(label='담기/빼기', placeholder='담기')
    ticker = discord.ui.TextInput(label='종목', placeholder='AAPL')
    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        act, t = self.action.value.strip(), self.ticker.value.upper()
        if uid not in user_portfolios: user_portfolios[uid] = []
        if act == "담기" and t not in user_portfolios[uid]: user_portfolios[uid].append(t)
        elif act != "담기" and t in user_portfolios[uid]: user_portfolios[uid].remove(t)
        await interaction.response.send_message(f"✅ {t} 서재 반영 완료!", ephemeral=True)

class AdvancedSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="🛠️ 15대 퀀트 툴 모음 (선택)", min_values=1, max_values=1, options=[
            discord.SelectOption(label="📖 쉬운 주식/경제 용어 사전", emoji="📖"), discord.SelectOption(label="💸 자투리 돈 스노우볼", emoji="💸"),
            discord.SelectOption(label="🛑 FOMO 방지 & 눌림목", emoji="🛑"), discord.SelectOption(label="🕵️ CEO 내부자 거래", emoji="👀"),
            discord.SelectOption(label="💥 공매도 스퀴즈 탐지기", emoji="💥"), discord.SelectOption(label="🌊 스마트 머니 수급", emoji="🌊"),
            discord.SelectOption(label="🔍 AI 캔들스틱 스캐너", emoji="🕯️"), discord.SelectOption(label="📉 MDD 백테스트", emoji="📉"),
            discord.SelectOption(label="🧠 AI 팩트 DB 열람", emoji="🤖")
        ])
    async def callback(self, interaction: discord.Interaction):
        if "DB" in self.values[0]:
            await interaction.response.defer()
            facts = "\n".join([f"- {f}" for f in knowledge_base['verified_facts'][-10:]])
            return await interaction.followup.send(embed=discord.Embed(title="🧠 팩트 DB", description=facts if facts else "수집 중...", color=0x0050FF))
        
        class ToolModal(discord.ui.Modal, title=f'🛠️ {self.values[0][:40]}'):
            val = discord.ui.TextInput(label='종목/단어/금액 입력', placeholder='입력')
            async def on_submit(self, i: discord.Interaction):
                await i.response.defer()
                ans = await ask_ai_async(f"분석 대상: '{self.val.value}'. 선택 툴: '{self.title}'. 전문적으로 팩트 분석해.", "전문가")
                await i.followup.send(embed=discord.Embed(title=f"결과: {self.title}", description=ans, color=0x2b2d31))
        await interaction.response.send_modal(ToolModal())

class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="🛒 주문", style=discord.ButtonStyle.success, custom_id="o"))
        self.add_item(discord.ui.Button(label="🎯 스나이퍼", style=discord.ButtonStyle.danger, custom_id="s"))
        self.add_item(discord.ui.Button(label="👑 리포트", style=discord.ButtonStyle.secondary, custom_id="r"))
        self.add_item(discord.ui.Button(label="📚 내 서재", style=discord.ButtonStyle.secondary, custom_id="l"))
        self.add_item(discord.ui.Button(label="🔥 일지", style=discord.ButtonStyle.secondary, custom_id="h"))
        self.add_item(AdvancedSelect())
    async def interaction_check(self, i: discord.Interaction) -> bool:
        cid = i.data.get("custom_id")
        if cid == "o": await i.response.send_modal(QuantOrderModal())
        elif cid == "s": await i.response.send_modal(SniperModal())
        elif cid == "r": await i.response.send_modal(ReportModal())
        elif cid == "l": await i.response.send_modal(LibraryModal())
        elif cid == "h": await i.response.send_modal(HabitJournalModal())
        return True

@bot.command(name="시작")
async def start_cmd(ctx):
    await ctx.send(embed=discord.Embed(title="PRO 퀀트 터미널", description="완벽 최적화 버전", color=0x0050FF), view=DashboardView())

@bot.command(name="모닝콜등록")
async def register_morning(ctx):
    global morning_channel_id
    morning_channel_id = ctx.channel.id
    await ctx.send("✅ 아침 8시 모닝콜 설정 완료!")

@bot.command(name="내서재")
async def view_lib(ctx):
    uid = ctx.author.id
    if uid not in user_portfolios or not user_portfolios[uid]: return await ctx.send("📚 서재가 비어있습니다.")
    m = await ctx.send("데이터 수집 중...")
    emb = discord.Embed(title=f"📚 서재 브리핑", color=0x0050FF)
    for t in user_portfolios[uid]:
        h = await fetch_stock_async(t, "1d")
        if h is not None: emb.add_field(name=t, value=f"${h['Close'].iloc[-1]:.2f}", inline=False)
    await m.edit(content=None, embed=emb)

bot.run(DISCORD_TOKEN)
