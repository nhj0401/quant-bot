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
        self.wfile.write("🔥 Quant Bot V35.0 (Zombie Bulldog System) is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 🔒 환경 변수: 모든 API 키 영혼까지 끌어모으기
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

raw_keys = []
if os.environ.get('GEMINI_API_KEY'): raw_keys.append(os.environ.get('GEMINI_API_KEY'))
for i in range(1, 11):
    if os.environ.get(f'GEMINI_API_KEY_{i}'): raw_keys.append(os.environ.get(f'GEMINI_API_KEY_{i}'))
if os.environ.get('GEMINI_API_KEYS'):
    raw_keys.extend(os.environ.get('GEMINI_API_KEYS').split(','))

# 중복 키 완벽 제거
API_KEYS = list(set([k.strip() for k in raw_keys if k.strip()]))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ------------------------------------------
# 🗄️ 글로벌 데이터 & 서버 캐시
# ------------------------------------------
api_semaphore = asyncio.Semaphore(5)
data_cache, ai_response_cache = {}, {}  
user_savings, user_goals, exam_mode = {}, {}, {}
alert_channel_id = None
CACHE_TTL = 600  

@bot.event
async def on_ready():
    # 🌟 중복 검사 후 최종 장착된 키들의 보안 앞뒤 문자 확인
    masked_keys = [f"{k[:5]}...{k[-4:]}" for k in API_KEYS]
    print(f"🔥 V35.0 좀비 엔진 가동! (현재 장착된 통신망: {len(API_KEYS)}개)")
    print(f"📡 인식된 키 목록: {masked_keys}")
    
    if not memory_cleanup_task.is_running(): memory_cleanup_task.start()
    if not autonomous_recon.is_running(): autonomous_recon.start()

@tasks.loop(minutes=15.0)
async def memory_cleanup_task():
    curr = time.time()
    for k in [k for k, v in data_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del data_cache[k]
    for k in [k for k, v in ai_response_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del ai_response_cache[k]

def generate_progress_bar(current, total, length=15):
    if total <= 0: return "[오류: 목표 금액 0원]"
    ratio = min(current / total, 1.0)
    filled = int(ratio * length)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {ratio * 100:.1f}%"

def get_loading_embed():
    return discord.Embed(
        title="⏳ 퀀트 AI 분석 진행 중...", 
        description="실시간 데이터를 스캔하며 최적의 전술을 도출하고 있습니다.\n*(과부하 발생 시 봇이 백그라운드에서 돌파할 때까지 로딩이 길어질 수 있습니다.)*", 
        color=0x3498DB
    )

# ------------------------------------------
# ⚡ [무한 체력] 좀비 코어 엔진 (최대 5분 물고 늘어짐)
# ------------------------------------------
async def ask_ai_async(prompt, system_role):
    if not API_KEYS:
        return "🚨 구글 API 키가 등록되지 않았습니다."

    cache_key = f"{system_role}_{prompt}"
    curr = time.time()
    if cache_key in ai_response_cache and (curr - ai_response_cache[cache_key]['timestamp']) < CACHE_TTL:
        return ai_response_cache[cache_key]['text']

    master_system_role = f"""너는 고등학교 1학년 트레이더를 위한 'AI 퀀트 및 멘탈 케어 비서'야. 
자본금 1~5만 원 단위의 소수점 투자(DCA)를 가장 효율적으로 리딩하며, 단타와 멘탈 방어 전술에 능해.
트레이더님은 경찰/특수부대를 꿈꾸며 체력(턱걸이, 푸시업, 유도)을 단련하듯 시드머니를 굴리고 있어.
[역할 지정]: {system_role}
[출력 원칙]: 마크다운 표 적극 활용, 수치화, 팩트 기반 요약."""

    payload = {
        "contents": [{"parts": [{"text": f"{master_system_role}\n\n{prompt}"}]}],
        "generationConfig": {"temperature": 0.7}
    }
    
    fast_models = ["gemini-1.5-flash", "gemini-2.0-flash"]
    
    async with api_semaphore:
        async with aiohttp.ClientSession() as session:
            # 🌟 무한 체력 로직: 60번 반복 * 5초 대기 = 최대 5분(300초) 동안 절대 안 멈추고 찌릅니다.
            for attempt in range(60):
                for api_key in API_KEYS:
                    for model_name in fast_models:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                        try:
                            async with session.post(url, json=payload, timeout=8.0) as res:
                                if res.status == 200:
                                    data = await res.json()
                                    ans_text = data['candidates'][0]['content']['parts'][0]['text']
                                    ai_response_cache[cache_key] = {'text': ans_text, 'timestamp': time.time()}
                                    return ans_text
                                elif res.status == 429:
                                    break # 429 뜨면 즉시 다음 키 장착!
                        except Exception:
                            continue 
                
                # 모든 키가 한계에 달했다면? (1분 제한 걸림)
                # 절대 포기하지 않고 5초 숨 고른 뒤, 첫 번째 키부터 다시 장전하고 쏩니다!
                await asyncio.sleep(5)
                
            # 디스코드 응답 제한 시간(15분)을 고려하여 5분이 넘어가면 최후의 안내 (이론상 안 뜹니다)
            return f"🚨 **[응답 지연]** 구글 서버가 5분 이상 응답하지 않습니다. 일시적인 장애일 수 있으니 나중에 다시 시도해주세요."

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
# 🛰️ 24시간 자율 정찰
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
                detected.append(f"[{t}] 거래량 폭발 (변동: {prc_change:+.2f}%)")
        except: continue

    if detected:
        prompt = f"포착 내용:\n{chr(10).join(detected)}\n이 현상이 투매인지 환희인지 1~10점으로 평가하고 브리핑해라."
        ans = await ask_ai_async(prompt, "정찰 레이더")
        await ch.send(embed=discord.Embed(title="🚨 [긴급] 수급 이상 징후 포착", description=ans, color=0xE74C3C))

# ------------------------------------------
# 🖥️ 상단 UI: 모달 (입력창 + 로딩 애니메이션)
# ------------------------------------------
class TickerSearchModal(discord.ui.Modal, title='🔍 종목 코드(티커) 검색기'):
    company_name = discord.ui.TextInput(label='회사 이름 (예: 애플, 팔란티어)', placeholder='이름을 입력하세요')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        name = self.company_name.value
        prompt = f"회사명 '{name}'의 미국 주식 공식 종목 코드(티커)를 찾아줘. 그리고 1줄로 요약해."
        ans = await ask_ai_async(prompt, "종목 검색 봇")
        await interaction.edit_original_response(embed=discord.Embed(title=f"🔍 '{name}' 검색 결과", description=ans, color=0x2ECC71))

class DCAModal(discord.ui.Modal, title='⚖️ 소수점 타점 (DCA & 단타)'):
    ticker = discord.ui.TextInput(label='매수할 주식 코드 (알파벳)', placeholder='예: TSLA')
    budget = discord.ui.TextInput(label='투입할 예산 (원)', placeholder='예: 15000')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ **[시험기간]** 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_loading_embed())
        t, bdg = self.ticker.value.upper(), float(self.budget.value.replace(',', ''))
        prompt = f"종목: {t}, 예산: {bdg:,.0f}원. 시장 상태 진단하고 매수 지시해."
        ans = await ask_ai_async(prompt, "전술 파트너")
        await interaction.edit_original_response(embed=discord.Embed(title=f"⚖️ {t} 매매 지시서", description=ans, color=0x2ECC71))

class SentimentModal(discord.ui.Modal, title='📰 뉴스 감성 분석 (공포/탐욕)'):
    ticker = discord.ui.TextInput(label='주식 코드', placeholder='예: AAPL')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}. 분위기를 종합해 '군중 심리'를 1~10점으로 평가해.", "감성 분석 AI")
        await interaction.edit_original_response(embed=discord.Embed(title="📰 심리 스캐너", description=ans, color=0x3498DB))

class PanicRoomModal(discord.ui.Modal, title='🧘 멘탈 방어선 (패닉 룸)'):
    ticker = discord.ui.TextInput(label='나를 불안하게 만드는 종목')
    reason = discord.ui.TextInput(label='불안한 이유', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 유저 패닉: '{self.reason.value}'. 멘탈 통제해.", "멘탈 케어 봇")
        await interaction.edit_original_response(embed=discord.Embed(title="🧘 멘탈 방어선 가동", description=ans, color=0x9B59B6))

class FinancialFilterButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📊 저평가 우량주 발굴", style=discord.ButtonStyle.secondary, custom_id="ff", row=1)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async("나스닥 빅테크 중 저평가 종목 2개를 골라 리포트를 제출해.", "필터링 AI")
        await interaction.edit_original_response(embed=discord.Embed(title="📊 저평가 리포트", description=ans, color=0xF1C40F))

class HabitJournalModal(discord.ui.Modal, title='📝 훈련 일지 & 시드 장부'):
    saved = discord.ui.TextInput(label='오늘 확보한 시드 (원)', placeholder='예: 1500')
    trade = discord.ui.TextInput(label='매매 복기', required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        uid = interaction.user.id
        amt = float(self.saved.value.replace(',', '')) if self.saved.value else 0
        user_savings[uid] = user_savings.get(uid, 0) + amt
        goal_text = f"\n\n🎯 **목표 진행률:** {generate_progress_bar(user_savings[uid], user_goals[uid]['price'])} ({user_savings[uid]:,.0f}원)" if uid in user_goals else ""
        ans = await ask_ai_async(f"확보 시드: {amt}원. 복기: '{self.trade.value}'. 멘탈 평가해.", "훈련 교관")
        await interaction.edit_original_response(embed=discord.Embed(title="🔥 단련 일지", description=ans + goal_text, color=0xFFD700))

class GoalSettingModal(discord.ui.Modal, title='🎯 목표 설정'):
    item = discord.ui.TextInput(label='목표 물건', placeholder='예: 나이키 가방')
    price = discord.ui.TextInput(label='목표 금액 (원)', placeholder='예: 50000')
    async def on_submit(self, interaction: discord.Interaction):
        user_goals[interaction.user.id] = {'item': self.item.value, 'price': float(self.price.value.replace(',', ''))}
        await interaction.response.send_message("🎯 **목표 설정 완료!** 일지에 반영됩니다.", ephemeral=True)

# ------------------------------------------
# 💡 하단 고급 드롭다운
# ------------------------------------------
class QuantToolModal(discord.ui.Modal):
    def __init__(self, tool_name: str):
        super().__init__(title=f'🛠️ {tool_name[:30]}')
        self.tool_name = tool_name
        self.input_val = discord.ui.TextInput(label='분석 대상 (종목/단어 등)')
        self.add_item(self.input_val)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"선택 툴: '{self.tool_name}', 대상: '{self.input_val.value.upper()}'. 전술적 분석해.", "퀀트 파트너")
        await interaction.edit_original_response(embed=discord.Embed(title=f"결과: {self.tool_name}", description=ans, color=0x95A5A6))

class AdvancedSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 🩺 재무 엑스레이 스캔"),
            discord.SelectOption(label="2. 📡 세력 급증 레이더"),
            discord.SelectOption(label="3. 💸 타임머신 스노우볼"),
            discord.SelectOption(label="4. 💥 숏커버링 폭발 예측"),
            discord.SelectOption(label="5. 💣 상폐/지뢰밭 필터")
        ]
        super().__init__(placeholder="👑 추가 고급 퀀트 툴 모음 (상세 분석)", min_values=1, max_values=1, options=options)
        
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_modal(QuantToolModal(tool_name=self.values[0]))

# ------------------------------------------
# 🎛️ 대시보드 세팅
# ------------------------------------------
class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="⚖️ 매수 타점", style=discord.ButtonStyle.success, custom_id="dca", row=0))
        self.add_item(discord.ui.Button(label="📰 감성 분석", style=discord.ButtonStyle.secondary, custom_id="sen", row=0))
        self.add_item(discord.ui.Button(label="🧘 패닉 룸", style=discord.ButtonStyle.danger, custom_id="pan", row=0))
        
        self.add_item(discord.ui.Button(label="🔍 종목 검색기", style=discord.ButtonStyle.primary, custom_id="search", row=1))
        self.add_item(FinancialFilterButton())
        self.add_item(discord.ui.Button(label="📝 단련 일지", style=discord.ButtonStyle.secondary, custom_id="hab", row=1))
        
        self.add_item(discord.ui.Button(label="🎯 목표 설정", style=discord.ButtonStyle.success, custom_id="goal", row=2))
        self.add_item(discord.ui.Button(label="🛡️ 시험기간 모드", style=discord.ButtonStyle.primary, custom_id="exam", row=2))
        self.add_item(discord.ui.Button(label="📡 상황실 등록", style=discord.ButtonStyle.danger, custom_id="alert", row=2))
        self.add_item(AdvancedSelect()) 

    async def interaction_check(self, i: discord.Interaction) -> bool:
        cid = i.data.get("custom_id")
        if cid == "dca": await i.response.send_modal(DCAModal())
        elif cid == "sen": await i.response.send_modal(SentimentModal())
        elif cid == "pan": await i.response.send_modal(PanicRoomModal())
        elif cid == "hab": await i.response.send_modal(HabitJournalModal())
        elif cid == "search": await i.response.send_modal(TickerSearchModal())
        elif cid == "goal": await i.response.send_modal(GoalSettingModal())
        elif cid == "exam":
            uid = i.user.id
            if exam_mode.get(uid, False):
                exam_mode[uid] = False
                await i.response.send_message("🔓 **[모드 해제]** 훈련 복귀.", ephemeral=True)
            else:
                exam_mode[uid] = True
                await i.response.send_message("🛡️ **[시험 모드 가동]** 매매 접근 차단.", ephemeral=True)
        elif cid == "alert":
            global alert_channel_id
            alert_channel_id = i.channel.id
            await i.response.send_message("📡 **[상황실 등록 완료]** 24시간 감시망 가동.")
        return True

# ------------------------------------------
# 📌 명령어 및 도움말
# ------------------------------------------
@bot.command(name="시작")
async def start_cmd(ctx):
    embed = discord.Embed(
        title="PRO 퀀트 터미널 (V35.0 무한 체력 좀비 모드)", 
        description="🔥 **[절대 포기 안 함]**\n과부하가 걸려도 에러를 띄우지 않고, 화면 뒤에서 최대 5분 동안 좀비처럼 물고 늘어져 정답을 토해냅니다.\n❓ **`!도움말`**을 치면 전체 사용법이 나옵니다.", 
        color=0x0050FF
    )
    await ctx.send(embed=embed, view=DashboardView())

@bot.command(name="도움말")
async def help_cmd(ctx):
    help_text = """
**🤖 V35.0 마스터 퀀트 비서 사용법**
...
"""
    embed = discord.Embed(title="📖 V35.0 마스터 가이드", description=help_text, color=0xF1C40F)
    await ctx.send(embed=embed)

bot.run(DISCORD_TOKEN)
