import discord
from discord.ext import commands, tasks
import yfinance as yf
import math
import asyncio
import time
import datetime
import os
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ==========================================
# 🌐 24시간 생존 웹서버
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("🔥 Quant Bot V24.0 (Grand Master) is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 🔒 환경 변수 및 봇 설정
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ------------------------------------------
# 🗄️ 글로벌 데이터 & 서버 캐시
# ------------------------------------------
api_semaphore = asyncio.Semaphore(5)
data_cache, ai_response_cache = {}, {}  
user_savings = {}
user_goals = {}   # 목표 {uid: {'item': '물건', 'price': 50000}}
exam_mode = {}    # 시험기간 차단 모드
alert_channel_id = None
CACHE_TTL = 600  

@bot.event
async def on_ready():
    print(f'🔥 V24.0 그랜드 마스터(기능 대통합) 접속 완료: {bot.user.name}')
    if not memory_cleanup_task.is_running(): memory_cleanup_task.start()
    if not autonomous_recon.is_running(): autonomous_recon.start()

@tasks.loop(minutes=15.0)
async def memory_cleanup_task():
    curr = time.time()
    for k in [k for k, v in data_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del data_cache[k]
    for k in [k for k, v in ai_response_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del ai_response_cache[k]

def generate_progress_bar(current, total, length=15):
    if total <= 0: return "[오류: 목표 금액이 0원]"
    ratio = min(current / total, 1.0)
    filled = int(ratio * length)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {ratio * 100:.1f}%"

# ------------------------------------------
# ⚡ [초고속 직통망] AI 코어 엔진
# ------------------------------------------
async def ask_ai_async(prompt, system_role):
    cache_key = f"{system_role}_{prompt}"
    curr = time.time()
    if cache_key in ai_response_cache and (curr - ai_response_cache[cache_key]['timestamp']) < CACHE_TTL:
        return ai_response_cache[cache_key]['text']

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    master_system_role = f"""너는 고등학교 1학년 트레이더를 위한 'AI 퀀트 및 멘탈 케어 비서'야. 
자본금 1~5만 원 단위의 소수점 투자(DCA)를 가장 효율적으로 리딩하며, 단타와 멘탈 방어 전술에 모두 능해.
트레이더님은 특수부대와 경찰을 꿈꾸며 체력(턱걸이, 푸시업, 유도 1단)을 단련하듯 시드머니를 단련 중이야.
원칙이 흔들릴 땐 턱걸이 한 개를 더 당기는 고통과 인내심에 비유해서 강력하게 팩트폭격과 멘탈 케어를 해줘.

[역할 지정]: {system_role}
[출력 원칙]: 마크다운 표 적극 활용, 수치화, 구체적인 소수점/단타 금액 지시."""

    payload = {
        "contents": [{"parts": [{"text": f"{master_system_role}\n\n{prompt}"}]}],
        "generationConfig": {"temperature": 0.7}
    }
    
    async with api_semaphore:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=20.0) as res:
                    if res.status == 200:
                        data = await res.json()
                        ans_text = data['candidates'][0]['content']['parts'][0]['text']
                        ai_response_cache[cache_key] = {'text': ans_text, 'timestamp': curr}
                        return ans_text
                    else:
                        return f"🚨 API 에러 ({res.status})"
        except Exception as e:
            return f"🚨 통신 실패: {e}"

async def fetch_stock_async(ticker, period="5d"):
    curr = time.time()
    if ticker in data_cache and (curr - data_cache[ticker]['timestamp']) < CACHE_TTL: return data_cache[ticker]['data']
    async with api_semaphore:
        try:
            hist = await asyncio.to_thread(yf.Ticker(ticker).history, period=period)
            if not hist.empty: data_cache[ticker] = {'data': hist, 'timestamp': curr}
            return hist
        except: return None

# ------------------------------------------
# 🛰️ 24시간 자율 정찰 (상황실 알림)
# ------------------------------------------
@tasks.loop(minutes=30.0)
async def autonomous_recon():
    if not alert_channel_id: return
    ch = bot.get_channel(alert_channel_id)
    if not ch: return
    watch_list = ["TSLA", "NVDA", "SOXL", "AAPL", "SPY"]
    detected = []
    for t in watch_list:
        try:
            hist = await fetch_stock_async(t, "5d")
            if hist is None or len(hist) < 2: continue
            vol_today, vol_yest = hist['Volume'].iloc[-1], hist['Volume'].iloc[-2]
            if vol_yest > 0 and (vol_today / vol_yest) >= 1.8: 
                prc_change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                detected.append(f"[{t}] 거래량 1.8배 이상 폭발 (변동: {prc_change:+.2f}%)")
        except: continue

    if detected:
        prompt = f"무인 정찰 포착 내용:\n{chr(10).join(detected)}\n이 현상이 투매인지 환희인지 감성 점수(1~10)로 평가하고 소수점/단타 타점인지 브리핑해라."
        ans = await ask_ai_async(prompt, "무인 정찰 레이더")
        await ch.send(embed=discord.Embed(title="🚨 [긴급] 자율 정찰 상황 갱신", description=ans, color=0xE74C3C))

# ------------------------------------------
# 🖥️ 상단 UI: 설계도 코어 + 일지
# ------------------------------------------
class SentimentModal(discord.ui.Modal, title='📰 뉴스 감성 분석 (Sentiment AI)'):
    ticker = discord.ui.TextInput(label='관심 주식 코드 (예: TSLA)', placeholder='티커 입력')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        t = self.ticker.value.upper()
        hist = await fetch_stock_async(t, "5d")
        prc_change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100 if hist is not None else 0
        prompt = f"종목: {t}, 5일 변동: {prc_change:+.2f}%. 최근 시장 분위기를 종합해 '군중 심리(감성 점수)'를 1~10점(1:극도 공포, 10:극도 환희)으로 평가해."
        ans = await ask_ai_async(prompt, "뉴스 감성 분석 AI")
        await interaction.followup.send(embed=discord.Embed(title=f"📰 {t} 심리 스캐너", description=ans, color=0x3498DB))

class DCAModal(discord.ui.Modal, title='⚖️ 소수점 타점 (DCA & 단타)'):
    ticker = discord.ui.TextInput(label='매수할 주식 코드', placeholder='예: SPY, AAPL')
    budget = discord.ui.TextInput(label='투입할 예산 (원)', placeholder='예: 15000')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False):
            return await interaction.response.send_message("🛡️ **[시험기간 모드]** 차트 접근이 차단되었습니다. 공부하십시오.", ephemeral=True)
        await interaction.response.defer()
        t, bdg = self.ticker.value.upper(), float(self.budget.value.replace(',', ''))
        prompt = f"종목: {t}, 예산: {bdg:,.0f}원. 시장 감성 상태를 진단하고, 이 예산을 오늘 토스에서 얼마치 매수할지 구체적인 단가/금액을 지시해."
        ans = await ask_ai_async(prompt, "소액 매매 전술 파트너")
        await interaction.followup.send(embed=discord.Embed(title=f"⚖️ {t} 소수점 매매 지시서", description=ans, color=0x2ECC71))

class PanicRoomModal(discord.ui.Modal, title='🧘 멘탈 방어선 (패닉 룸)'):
    ticker = discord.ui.TextInput(label='나를 불안하게 만드는 종목', placeholder='예: TSLA')
    reason = discord.ui.TextInput(label='불안한 이유', style=discord.TextStyle.paragraph, placeholder='예: 갑자기 떨어져서 팔고 싶어')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        prompt = f"종목: {self.ticker.value.upper()}, 유저의 패닉: '{self.reason.value}'. 공포에 질린 트레이더에게 체력 단련(턱걸이 한계 극복 등)에 비유하여 강력하게 멘탈을 통제해."
        ans = await ask_ai_async(prompt, "강철 멘탈 케어 봇")
        await interaction.followup.send(embed=discord.Embed(title="🧘 멘탈 방어선 가동", description=ans, color=0x9B59B6))

class FinancialFilterButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📊 저평가 우량주 발굴", style=discord.ButtonStyle.primary, custom_id="ff", row=1)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False):
            return await interaction.response.send_message("🛡️ **[시험기간 모드]** 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.defer()
        prompt = f"나스닥 빅테크 중, 현재 시점에서 PER, 이익률 대비 주가가 싸진 저평가 종목 2개를 골라 필터링 보고서를 제출해."
        ans = await ask_ai_async(prompt, "재무제표 필터링 AI")
        await interaction.followup.send(embed=discord.Embed(title="📊 저평가 타겟 리포트", description=ans, color=0xF1C40F))

class HabitJournalModal(discord.ui.Modal, title='📝 훈련 일지 & 시드 장부'):
    saved = discord.ui.TextInput(label='오늘 확보한 총알(시드) (원)', placeholder='예: 1500')
    trade = discord.ui.TextInput(label='오늘의 매매/원칙 준수 여부', placeholder='예: 공포장 멘탈 방어 성공', required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = interaction.user.id
        amt = float(self.saved.value.replace(',', '')) if self.saved.value else 0
        user_savings[uid] = user_savings.get(uid, 0) + amt
        
        goal_text = ""
        if uid in user_goals:
            goal = user_goals[uid]
            progress = generate_progress_bar(user_savings[uid], goal['price'])
            goal_text = f"\n\n🎯 **[{goal['item']}] 목표 진행률:**\n{progress} ({user_savings[uid]:,.0f}원)"

        prompt = f"확보 시드: {amt}원 (누적: {user_savings[uid]}원). 일지: '{self.trade.value}'. 푼돈을 모아 우량주를 사는 훈련을 잘 지켰는지 체력 단련에 비유해 평가해."
        ans = await ask_ai_async(prompt, "훈련 교관")
        await interaction.followup.send(embed=discord.Embed(title=f"🔥 {interaction.user.name}님의 단련 일지", description=ans + goal_text, color=0xFFD700))

# ------------------------------------------
# 💡 하단 UI: 드롭다운 고급 툴 (부활!)
# ------------------------------------------
class QuantToolModal(discord.ui.Modal):
    def __init__(self, tool_name: str):
        super().__init__(title=f'🛠️ {tool_name[:30]}')
        self.tool_name = tool_name
        self.input_val = discord.ui.TextInput(label='분석 대상 (종목/단어 등)', placeholder='예: AAPL')
        self.add_item(self.input_val)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        val = self.input_val.value.upper()
        prompt = f"선택 툴: '{self.tool_name}', 대상: '{val}'. 이 툴의 목적에 맞춰 전술적이고 팩트 위주의 결과를 도출해."
        ans = await ask_ai_async(prompt, "퀀트 파트너")
        await interaction.followup.send(embed=discord.Embed(title=f"결과: {self.tool_name}", description=ans, color=0x95A5A6))

class AdvancedSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 🩺 재무 엑스레이 스캔", description="겉매출과 속이익 뼈대 스캔"),
            discord.SelectOption(label="2. 📡 거래량/세력 급증 레이더", description="돈이 몰리는 모멘텀 포착"),
            discord.SelectOption(label="3. 💸 타임머신 스노우볼", description="과거부터 모았다면 지금 얼마?"),
            discord.SelectOption(label="4. 💥 숏커버링 (항복) 예측", description="세력 기권 폭등 타점 판독"),
            discord.SelectOption(label="5. 💣 상폐/지뢰밭 필터", description="위험한 재무 쓰레기 판별")
        ]
        super().__init__(placeholder="👑 추가 고급 퀀트 툴 모음 (선택)", min_values=1, max_values=1, options=options)
        
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False):
            return await interaction.response.send_message("🛡️ **[시험기간 모드]** 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_modal(QuantToolModal(tool_name=self.values[0]))

class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="⚖️ 매수/단타 타점", style=discord.ButtonStyle.success, custom_id="dca", row=0))
        self.add_item(discord.ui.Button(label="📰 뉴스 감성 분석", style=discord.ButtonStyle.secondary, custom_id="sen", row=0))
        self.add_item(discord.ui.Button(label="🧘 패닉 룸 (방어선)", style=discord.ButtonStyle.danger, custom_id="pan", row=0))
        
        self.add_item(FinancialFilterButton())
        self.add_item(discord.ui.Button(label="📝 단련 일지 (시드 장부)", style=discord.ButtonStyle.secondary, custom_id="hab", row=1))
        
        self.add_item(AdvancedSelect()) # 고급 툴 드롭다운 복구!

    async def interaction_check(self, i: discord.Interaction) -> bool:
        cid = i.data.get("custom_id")
        if cid == "dca": await i.response.send_modal(DCAModal())
        elif cid == "sen": await i.response.send_modal(SentimentModal())
        elif cid == "pan": await i.response.send_modal(PanicRoomModal())
        elif cid == "hab": await i.response.send_modal(HabitJournalModal())
        return True

# ------------------------------------------
# 📌 명령어 모음 & 상세 도움말 (부활!)
# ------------------------------------------
@bot.command(name="시작")
async def start_cmd(ctx):
    embed = discord.Embed(
        title="PRO 퀀트 터미널 (V24.0 그랜드 마스터)", 
        description="🔥 완벽 설계도(Blueprint)와 모든 고급 기능이 통합되었습니다.\n❓ 봇 사용법이 궁금하다면 **`!도움말`**을 입력하세요.", 
        color=0x0050FF
    )
    await ctx.send(embed=embed, view=DashboardView())

@bot.command(name="도움말")
async def help_cmd(ctx):
    help_text = """
**🤖 고1 트레이더를 위한 AI 퀀트 비서 사용법**

**1️⃣ 상단 핵심 무기 (버튼 5개)**
*   ⚖️ **매수/단타 타점:** 살 주식과 예산을 적으면 환율을 계산해 소수점 진입 단가를 알려줍니다.
*   📰 **뉴스 감성 분석:** AI가 실시간 분위기를 긁어와 대중이 공포(1점)인지 환희(10점)인지 스캔합니다.
*   🧘 **패닉 룸 (멘탈):** 폭락장에 멘탈이 나갔을 때 누르세요. 뼈 때리는 조언으로 원칙을 지켜줍니다.
*   📊 **저평가 발굴:** 지금 나스닥에서 주워 담을 만한 할인 종목 2개를 알아서 찾아옵니다.
*   📝 **단련 일지:** 푼돈 아낀 걸 적으면 경험치/목표 진행률이 오릅니다.

**2️⃣ 하단 고급 툴 (드롭다운 메뉴)**
*   재무 엑스레이, 타임머신 복리 계산, 지뢰밭 탐지 등 세부적인 차트/재무 분석 툴이 5개 숨겨져 있습니다.

**3️⃣ 특수 명령어 시스템 (채팅창에 입력)**
*   `!상황실등록` : 이걸 치면 봇이 24시간 거래량 터진 종목을 감시하다가 알람을 보내줍니다.
*   `!시험기간` : 중간고사 돌입! 모든 차트 접근을 차단하고 봇이 대신 감시합니다. 다시 치면 해제됩니다.
*   `!목표설정 <가격> <물건명>` : (예: `!목표설정 50000 나이키가방`) 일지를 쓸 때마다 달성률 게이지 바가 차오릅니다!
"""
    embed = discord.Embed(title="📖 V24.0 통합 마스터 가이드", description=help_text, color=0xF1C40F)
    await ctx.send(embed=embed)

@bot.command(name="상황실등록")
async def set_alert_channel(ctx):
    global alert_channel_id
    alert_channel_id = ctx.channel.id
    await ctx.send("📡 **[상황실 등록 완료]**\n24시간 무인 정찰기가 가동됩니다. 이상 징후 발생 시 이곳으로 보고합니다.")

@bot.command(name="목표설정")
async def set_goal_cmd(ctx, price: int = None, *, item: str = None):
    if not price or not item:
        return await ctx.send("🚨 명령어 오류! `!목표설정 50000 프로틴` 형식으로 입력하십시오.")
    uid = ctx.author.id
    user_goals[uid] = {'item': item, 'price': price}
    await ctx.send(f"🎯 **레이더 설정 완료:** [{item}] (목표: {price:,.0f}원)\n일지를 쓸 때마다 진행률이 추적됩니다.")

@bot.command(name="시험기간")
async def exam_mode_cmd(ctx):
    uid = ctx.author.id
    if exam_mode.get(uid, False):
        exam_mode[uid] = False
        await ctx.send("🔓 **[시험기간 모드 해제]** 훈련 복귀를 환영합니다.")
    else:
        exam_mode[uid] = True
        await ctx.send("🛡️ **[시험기간 모드 가동]** 학업 전선에 집중하십시오. 매매 접근이 차단됩니다.")

bot.run(DISCORD_TOKEN)
