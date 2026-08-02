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
        self.wfile.write("🔥 Quant Bot V41.0 (NY Time-Watch) is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 🔒 환경 변수: 초고속 Groq 엔진
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY') 

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

# 🌟 실시간 미국 증시 타임워치 (한국 시간 24시간 기준)
def get_market_status():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    now_str = now.strftime(f"%Y년 %m월 %d일 {weekdays[now.weekday()]} %H:%M")
    
    is_summer = 3 <= now.month <= 11
    open_h, open_m = (22, 30) if is_summer else (23, 30)
    close_h = 5 if is_summer else 6
    
    curr_mins = now.hour * 60 + now.minute
    open_mins = open_h * 60 + open_m
    close_mins = close_h * 60
    
    wd = now.weekday() # 0:월 ~ 6:일
    
    is_closed = False
    if wd == 5 and curr_mins >= close_mins: # 토요일 아침 마감 이후
        is_closed = True
    elif wd == 6: # 일요일
        is_closed = True
    elif wd == 0 and curr_mins < open_mins: # 월요일 개장 전
        is_closed = True
        
    if is_closed:
        return now_str, f"💤 **현재 미국 증시는 [주말 휴장]입니다.** (다음 개장: 월요일 {open_h}:{open_m})"
    
    if curr_mins < close_mins:
        return now_str, f"🔥 **미국 증시 [정규장 진행 중]** (마감: 오늘 {close_h:02d}:00)"
    elif curr_mins >= open_mins:
        return now_str, f"🔥 **미국 증시 [정규장 진행 중]** (마감: 내일 {close_h:02d}:00)"
    else:
        return now_str, f"⏳ **현재 [프리마켓 / 대기장]** (개장: 오늘 {open_h}:{open_m})"

@bot.event
async def on_ready():
    print(f"🔥 V41.0 뉴욕 타임워치 및 토스 단타 무기고 가동 완료!")
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
    _, market_msg = get_market_status()
    return discord.Embed(
        title="⚡ 초고속 퀀트 AI 분석 중...", 
        description=f"Llama-3 엔진이 데이터를 스캔 중입니다. 상세한 브리핑을 준비 중이니 대기하십시오.\n\n🕒 {market_msg}", 
        color=0x3498DB
    )

def get_nuke_loading_embed():
    _, market_msg = get_market_status()
    return discord.Embed(
        title="☢️ [오메가 프로토콜] 가동 중...", 
        description=f"모든 지표와 심리를 응축하여 최종 작전 명령서를 작성하고 있습니다. 대기하십시오.\n\n🕒 {market_msg}", 
        color=0xE74C3C
    )

# ------------------------------------------
# ⚡ 초고속 Groq API 코어 (토스 맞춤형)
# ------------------------------------------
async def ask_ai_async(prompt, system_role):
    if not GROQ_API_KEY: return "🚨 GROQ API 키가 Render에 등록되지 않았습니다."
    cache_key = f"{system_role}_{prompt}"
    curr = time.time()
    if cache_key in ai_response_cache and (curr - ai_response_cache[cache_key]['timestamp']) < CACHE_TTL:
        return ai_response_cache[cache_key]['text']

    master_system_role = f"""너는 고등학교 1학년 트레이더를 위한 'AI 퀀트 참모'야. 
자본금 1~5만 원 단위의 소수점 투자 및 '토스(Toss) 증권 앱'을 이용한 단타(CQB)에 능해. 
토스 앱은 호가창이 얇게 보이고 체결 딜레이가 있으므로, 뇌동매매를 극도로 경계하고 유도에서 확실한 깃을 잡았을 때만 메어치듯 확실한 자리에서만 진입하도록 지시해.
트레이더님은 특수부대와 경찰을 꿈꾸며 체력을 단련하고 있어.
[역할 지정]: {system_role}
[출력 원칙]: 반드시 한국어로 답변. 이유와 원리를 고등학생 눈높이에서 아주 상세하게 설명할 것. 마크다운 표 적극 활용. 특수작전과 헬스/유도에 빗대어 엄격하고 날카롭게 조언해라."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama3-70b-8192", 
        "messages": [
            {"role": "system", "content": master_system_role},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    async with api_semaphore:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=15.0) as res:
                    if res.status == 200:
                        data = await res.json()
                        ans_text = data['choices'][0]['message']['content']
                        ai_response_cache[cache_key] = {'text': ans_text, 'timestamp': time.time()}
                        return ans_text
                    else:
                        return f"🚨 통신 오류 ({res.status})"
            except Exception as e:
                return f"🚨 네트워크 통신 실패: {e}"

# ------------------------------------------
# 🖥️ UI 모달들
# ------------------------------------------
class TickerSearchModal(discord.ui.Modal, title='🔍 종목 검색'):
    company_name = discord.ui.TextInput(label='회사명', placeholder='예: 애플')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"'{self.company_name.value}'의 미국 주식 코드를 찾고, 고등학생이 이해하기 쉽게 비즈니스 모델을 상세히 설명해.", "검색 봇")
        await interaction.edit_original_response(embed=discord.Embed(title="🔍 검색 결과", description=ans, color=0x2ECC71))

class DCAModal(discord.ui.Modal, title='⚖️ 매수 타점'):
    ticker = discord.ui.TextInput(label='주식 코드')
    budget = discord.ui.TextInput(label='예산 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 예산: {self.budget.value}원. 토스 소수점 투자를 활용해 언제 어떻게 매수할지 구체적 전술을 설명해.", "전술 파트너")
        await interaction.edit_original_response(embed=discord.Embed(title=f"⚖️ {self.ticker.value.upper()} 매매 지시서", description=ans, color=0x2ECC71))

class PanicRoomModal(discord.ui.Modal, title='🧘 패닉 룸'):
    ticker = discord.ui.TextInput(label='불안한 종목')
    reason = discord.ui.TextInput(label='이유', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 이유: '{self.reason.value}'. 멘탈을 꽉 잡아주는 상세한 훈련 교관의 팩트폭격을 해라.", "훈련 교관")
        await interaction.edit_original_response(embed=discord.Embed(title="🧘 멘탈 방어선", description=ans, color=0x9B59B6))

class GoalSettingModal(discord.ui.Modal, title='🎯 목표 설정'):
    item = discord.ui.TextInput(label='목표 물건')
    price = discord.ui.TextInput(label='목표 금액 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        user_goals[interaction.user.id] = {'item': self.item.value, 'price': float(self.price.value.replace(',', ''))}
        await interaction.response.send_message("🎯 **목표 설정 완료!**", ephemeral=True)

class OmegaProtocolModal(discord.ui.Modal, title='☢️ 전술핵: 오메가 프로토콜'):
    ticker = discord.ui.TextInput(label='분석할 종목 코드')
    budget = discord.ui.TextInput(label='총예산 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_nuke_loading_embed())
        prompt = f"""종목: {self.ticker.value.upper()}, 예산: {self.budget.value}원. 토스(Toss) 앱 사용 중.
재무/차트/수급/심리를 융합해 '오메가 프로토콜'을 작성해라. 토스 환경에 맞게 며칠간 얼마씩 살지, 칼손절은 어디인지 수치로 하달해라."""
        ans = await ask_ai_async(prompt, "최고 사령관")
        await interaction.edit_original_response(embed=discord.Embed(title=f"☢️ [오메가 프로토콜] {self.ticker.value.upper()}", description=ans, color=0xE74C3C))

# ------------------------------------------
# 💡 툴 입력창용 모달
# ------------------------------------------
class QuantToolModal(discord.ui.Modal):
    def __init__(self, tool_name: str, category: str):
        super().__init__(title=f'🛠️ {tool_name[:30]}')
        self.tool_name = tool_name
        self.category = category
        self.input_val = discord.ui.TextInput(label='분석 대상 (종목 등)')
        self.add_item(self.input_val)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        if self.category == "daytrade":
            prompt = f"선택 툴: '{self.tool_name}', 대상: '{self.input_val.value.upper()}'. 토스(Toss) 앱으로 단타를 친다. 호가창이 불리한 점을 고려해 리스크와 단기 흐름을 구체적으로 분석하고 칼손절 원칙을 강조해라."
        else:
            prompt = f"선택 툴: '{self.tool_name}', 대상: '{self.input_val.value.upper()}'. 고등학교 1학년 눈높이에 맞춰 이 툴의 의미와 현재 종목에 어떻게 적용되는지 아주 상세하게 브리핑해라."
            
        ans = await ask_ai_async(prompt, "퀀트 맥가이버")
        await interaction.edit_original_response(embed=discord.Embed(title=f"결과: {self.tool_name}", description=ans, color=0x95A5A6))

# ------------------------------------------
# 🗂️ 드롭다운 3종 (일반 10 / 특수 10 / 단타 20)
# ------------------------------------------
class GeneralSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 🩺 재무 엑스레이 스캔"), discord.SelectOption(label="2. ⚖️ 손익비(RR) 계산기"),
            discord.SelectOption(label="3. ❄️ 배당금 복리 머신"), discord.SelectOption(label="4. 📊 섹터 테마 스캐너"),
            discord.SelectOption(label="5. 📰 호재/악재 팩트체크"), discord.SelectOption(label="6. 🏢 라이벌 비교 스캔"),
            discord.SelectOption(label="7. 📅 어닝(실적) 충격 분석"), discord.SelectOption(label="8. 📉 구조대(물타기) 계산기"),
            discord.SelectOption(label="9. 📈 ETF 방패막이 확인"), discord.SelectOption(label="10. 💰 10대 소액 맞춤 플래너")
        ]
        super().__init__(placeholder="🟢 [일반 훈련] 툴박스 (가치투자 & 기본기)", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        await interaction.response.send_modal(QuantToolModal(tool_name=self.values[0], category="general"))

class SpecialSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 📡 세력(고래) 수급 레이더"), discord.SelectOption(label="2. 🎯 스나이퍼 타점 (RSI)"),
            discord.SelectOption(label="3. 💸 타임머신 백테스트"), discord.SelectOption(label="4. 💥 숏커버링 폭발 예측"),
            discord.SelectOption(label="5. 💣 상폐 지뢰밭 탐지기"), discord.SelectOption(label="6. 🚀 내부자 매수 포착"),
            discord.SelectOption(label="7. 🦇 다크풀 그림자 추적"), discord.SelectOption(label="8. 🔥 광기 버블 경보"),
            discord.SelectOption(label="9. 🐺 야수의 심장 모드"), discord.SelectOption(label="10. 🕵️ VIX 폭락장 방어")
        ]
        super().__init__(placeholder="🔴 [특수 작전] 툴박스 (공격적 & 하이리스크)", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        await interaction.response.send_modal(QuantToolModal(tool_name=self.values[0], category="special"))

class DayTradeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. ⚡ 1분봉 스캘핑 타점 판독기"), discord.SelectOption(label="2. 🚀 시초가 갭상승 스나이퍼"),
            discord.SelectOption(label="3. 💣 거래량 폭발 돌파 매매"), discord.SelectOption(label="4. 🩸 급락 눌림목 암살 전술"),
            discord.SelectOption(label="5. 🛡️ -2% 칼손절 강제 탈출"), discord.SelectOption(label="6. 🧊 VI(변동성 완화) 예측"),
            discord.SelectOption(label="7. 📉 투매(설거지) 폭포수 경보"), discord.SelectOption(label="8. 🧠 뇌동매매(FOMO) 차단기"),
            discord.SelectOption(label="9. 💸 반익절(트레일링) 가이드"), discord.SelectOption(label="10. 🕵️ 장전 수급 스파이"),
            discord.SelectOption(label="11. ⚖️ 얇은 호가창 지뢰밭 탐지"), discord.SelectOption(label="12. 📊 VWAP 기준선 판독"),
            discord.SelectOption(label="13. 📉 쌍봉(고점) 하락 패턴 탐지"), discord.SelectOption(label="14. 🎣 밑꼬리 반등 낚시 전술"),
            discord.SelectOption(label="15. 💊 복수 매매 진정제"), discord.SelectOption(label="16. 🤖 프로그램 매크로 추적"),
            discord.SelectOption(label="17. 🙏 기도 매매 팩트 폭격기"), discord.SelectOption(label="18. 🏆 거래대금 싹쓸이 스캔"),
            discord.SelectOption(label="19. ⏳ 3분 홀딩 멘탈 테스트"), discord.SelectOption(label="20. 🐺 초변동성 심박수 측정")
        ]
        super().__init__(placeholder="⚡ [CQB 단타 전술] 무기고 (토스 최적화 / 칼손절 필수)", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        await interaction.response.send_modal(QuantToolModal(tool_name=self.values[0], category="daytrade"))

# ------------------------------------------
# 🎛️ 대시보드 UI 세팅
# ------------------------------------------
class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="🔍 검색", style=discord.ButtonStyle.primary, custom_id="search", row=0))
        self.add_item(discord.ui.Button(label="⚖️ 타점", style=discord.ButtonStyle.success, custom_id="dca", row=0))
        self.add_item(discord.ui.Button(label="🧘 패닉룸", style=discord.ButtonStyle.danger, custom_id="pan", row=0))
        self.add_item(discord.ui.Button(label="🎯 목표", style=discord.ButtonStyle.success, custom_id="goal", row=0))
        self.add_item(GeneralSelect()) 
        self.add_item(SpecialSelect()) 
        self.add_item(DayTradeSelect()) 
        self.add_item(discord.ui.Button(label="☢️ 오메가 프로토콜 (종합 작전서)", style=discord.ButtonStyle.danger, custom_id="omega", row=4))
        self.add_item(discord.ui.Button(label="🛡️ 시험모드", style=discord.ButtonStyle.primary, custom_id="exam", row=4))
        self.add_item(discord.ui.Button(label="📡 상황실", style=discord.ButtonStyle.secondary, custom_id="alert", row=4))

    async def interaction_check(self, i: discord.Interaction) -> bool:
        cid = i.data.get("custom_id")
        if cid == "dca": await i.response.send_modal(DCAModal())
        elif cid == "pan": await i.response.send_modal(PanicRoomModal())
        elif cid == "search": await i.response.send_modal(TickerSearchModal())
        elif cid == "goal": await i.response.send_modal(GoalSettingModal())
        elif cid == "omega": await i.response.send_modal(OmegaProtocolModal()) 
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
# 📌 명령어 및 백과사전
# ------------------------------------------
@bot.command(name="시작")
async def start_cmd(ctx):
    now_str, market_msg = get_market_status()
    embed = discord.Embed(
        title="PRO 퀀트 터미널 (V41.0 타임워치 장착)", 
        description=f"📅 **현재 시각:** {now_str}\n{market_msg}\n\n🔥 **[토스 환경 최적화]**\n모든 툴과 분석은 토스의 얇은 호가창 환경을 고려하여 뼈때리는 팩트로 브리핑합니다.\n❓ **`!도움말`**을 치면 전체 40종 툴의 상세 가이드가 나옵니다.", 
        color=0x0050FF
    )
    await ctx.send(embed=embed, view=DashboardView())

@bot.command(name="도움말")
async def help_cmd(ctx):
    help_text = """
**🤖 V41.0 특수부대 퀀트 비서 종합 가이드**

**1️⃣ 상단 코어 버튼 (필수 기능)**
*   🔍 **검색:** 영어 종목 코드를 찾아주고 회사가 뭐하는 곳인지 상세히 설명합니다.
*   ⚖️ **타점:** 토스로 모으는 소수점 주식의 오늘자 진입 전략을 짭니다.
*   🧘 **패닉룸:** 주가가 폭락해 불안할 때, 감정을 통제하고 팩트를 체크해 줍니다.
*   🎯 **목표:** 사고 싶은 물건과 가격을 등록해 동기부여를 세팅합니다.

**2️⃣ 🟢 [일반 훈련] 툴박스 (가치투자 & 펀더멘탈 10종)**
*   재무 안전성, 배당금 복리 시뮬레이션, 물타기 계산기 등 **우량주를 안전하게 장기 투자**할 때 필요한 상세 분석을 제공합니다.

**3️⃣ 🔴 [특수 작전] 툴박스 (하이리스크 추적 10종)**
*   세력 수급 레이더, 숏커버링(폭등) 예측, 상폐 지뢰밭 탐지 등 **기관과 고래들의 뒤통수를 치고 스나이퍼처럼 타점을 노릴 때** 씁니다.

**4️⃣ ⚡ [CQB 단타 전술] 툴박스 (토스 최적화 초단타 20종)**
*   1분봉 스캘핑, 시초가 갭상승, 뇌동매매 차단 등 **초단위 변동성에서 살아남기 위한 극한의 단타 전술**입니다. 토스 앱의 얇은 호가창 환경을 반영해 아주 뼈때리고 상세하게 분석해 줍니다.

**5️⃣ 하단 통제실 버튼**
*   ☢️ **오메가 프로토콜:** 재무/수급/차트/심리를 전부 갈아 넣어 **1장의 최종 작전 명령서**를 작성합니다.
*   🛡️ **시험모드:** 공부에 집중하기 위해 차트 접근을 강제로 막습니다.
"""
    embed = discord.Embed(title="📖 V41.0 백과사전 가이드", description=help_text, color=0xF1C40F)
    await ctx.send(embed=embed)

bot.run(DISCORD_TOKEN)
