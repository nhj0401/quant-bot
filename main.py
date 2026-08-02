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
        self.wfile.write("🔥 Quant Bot V44.0 (Anti-Hanja & Long/Short Arsenal) is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 🔒 환경 변수: 무결성 검증 (공백/줄바꿈 완벽 제거)
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '').strip()
raw_groq = os.environ.get('GROQ_API_KEY', '')
GROQ_API_KEY = raw_groq.replace('\n', '').replace('\r', '').strip()

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
    wd = now.weekday()
    
    is_closed = False
    if wd == 5 and curr_mins >= close_mins: is_closed = True
    elif wd == 6: is_closed = True
    elif wd == 0 and curr_mins < open_mins: is_closed = True
        
    if is_closed: return now_str, f"💤 **현재 미국 증시는 [주말 휴장]입니다.**"
    if curr_mins < close_mins: return now_str, f"🔥 **미국 증시 [정규장 진행 중]** (마감: 오늘 {close_h:02d}:00)"
    elif curr_mins >= open_mins: return now_str, f"🔥 **미국 증시 [정규장 진행 중]** (마감: 내일 {close_h:02d}:00)"
    else: return now_str, f"⏳ **현재 [프리마켓 / 대기장]** (개장: 오늘 {open_h}:{open_m})"

@bot.event
async def on_ready():
    print(f"🔥 V44.0 60종 무기고 및 한자 억제기 가동 완료!")
    if not memory_cleanup_task.is_running(): memory_cleanup_task.start()

@tasks.loop(minutes=15.0)
async def memory_cleanup_task():
    curr = time.time()
    for k in [k for k, v in data_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del data_cache[k]
    for k in [k for k, v in ai_response_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del ai_response_cache[k]

def get_loading_embed():
    _, market_msg = get_market_status()
    return discord.Embed(
        title="⚡ 초고속 퀀트 AI 분석 중...", 
        description=f"Llama-3 다중 칩셋 엔진이 스캔 중입니다.\n\n🕒 {market_msg}", 
        color=0x3498DB
    )

def get_nuke_loading_embed():
    _, market_msg = get_market_status()
    return discord.Embed(
        title="☢️ [오메가 프로토콜] 가동 중...", 
        description=f"모든 지표를 응축하여 최종 작전 명령서를 작성하고 있습니다.\n\n🕒 {market_msg}", 
        color=0xE74C3C
    )

# ------------------------------------------
# ⚡ 초고속 Groq API 코어 (한자 완전 박멸 락 장착)
# ------------------------------------------
async def ask_ai_async(prompt, system_role):
    if not GROQ_API_KEY: return "🚨 GROQ API 키가 Render에 등록되지 않았습니다."
    cache_key = f"{system_role}_{prompt}"
    curr = time.time()
    if cache_key in ai_response_cache and (curr - ai_response_cache[cache_key]['timestamp']) < CACHE_TTL:
        return ai_response_cache[cache_key]['text']

    master_system_role = f"""너는 고등학교 1학년 트레이더를 위한 'AI 퀀트 참모'야. 
자본금 1~5만 원 단위의 소수점 투자 및 '토스(Toss) 증권 앱'을 이용한 매매를 보좌해.
트레이더님은 특수부대와 경찰을 꿈꾸며 혹독하게 턱걸이와 유도로 체력을 단련하고 있어.
[역할 지정]: {system_role}
[언어 및 출력 절대 원칙]: 
1. 무조건 '한국어(Korean)'로만 답변하라. 
2. 🚨 중국어/일본어 한자 출력 절대 금지! (예: 相対力 -> 상대강도 / 账面 -> 장부금액(순자산) / 压力 -> 매도압력(저항선)으로 반드시 한국어 표준 증권 용어로 번역해서 쓸 것). 한자가 한 글자라도 섞이면 작전 실패로 간주한다.
3. 고등학생이 이해하기 쉽게 비유를 들어 아주 상세하게 설명할 것."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"]
    
    async with api_semaphore:
        async with aiohttp.ClientSession() as session:
            last_error = ""
            for model_name in models:
                payload = {
                    "model": model_name, 
                    "messages": [
                        {"role": "system", "content": master_system_role},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2048 
                }
                try:
                    async with session.post(url, headers=headers, json=payload, timeout=12.0) as res:
                        if res.status == 200:
                            data = await res.json()
                            ans_text = data['choices'][0]['message']['content']
                            ai_response_cache[cache_key] = {'text': ans_text, 'timestamp': time.time()}
                            return ans_text
                        elif res.status == 429:
                            continue 
                        else:
                            err_text = await res.text()
                            last_error = f"{res.status} | {err_text[:200]}"
                            continue 
                except Exception as e:
                    last_error = str(e)
                    continue
            return f"🚨 **[통신 오류]** 모든 엔진 타격 실패.\n🔍 **추적 결과:** `{last_error}`"

# ------------------------------------------
# 🖥️ UI 모달 (4,000자 에러 방어 적용)
# ------------------------------------------
class TickerSearchModal(discord.ui.Modal, title='🔍 종목 검색'):
    company_name = discord.ui.TextInput(label='회사명', placeholder='예: 애플')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"'{self.company_name.value}'의 미국 주식 코드를 찾고, 비즈니스 모델을 한국어로 설명해.", "검색 봇")
        await interaction.edit_original_response(embed=discord.Embed(title="🔍 검색 결과", description=ans[:4000], color=0x2ECC71))

class DCAModal(discord.ui.Modal, title='⚖️ 매수 타점'):
    ticker = discord.ui.TextInput(label='주식 코드')
    budget = discord.ui.TextInput(label='예산 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 예산: {self.budget.value}원. 매수 전술을 한국어로 짜줘.", "전술 파트너")
        await interaction.edit_original_response(embed=discord.Embed(title=f"⚖️ {self.ticker.value.upper()} 매매 지시서", description=ans[:4000], color=0x2ECC71))

class PanicRoomModal(discord.ui.Modal, title='🧘 패닉 룸'):
    ticker = discord.ui.TextInput(label='불안한 종목')
    reason = discord.ui.TextInput(label='이유', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 이유: '{self.reason.value}'. 한자 없이 팩트폭격해라.", "훈련 교관")
        await interaction.edit_original_response(embed=discord.Embed(title="🧘 멘탈 방어선", description=ans[:4000], color=0x9B59B6))

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
        prompt = f"종목: {self.ticker.value.upper()}, 예산: {self.budget.value}원. 토스 앱 사용 중. 재무/차트/수급/심리를 융합해 '오메가 프로토콜'을 한자 없이 작성해라."
        ans = await ask_ai_async(prompt, "최고 사령관")
        await interaction.edit_original_response(embed=discord.Embed(title=f"☢️ [오메가 프로토콜] {self.ticker.value.upper()}", description=ans[:4000], color=0xE74C3C))

class QuantToolModal(discord.ui.Modal):
    def __init__(self, tool_name: str, category: str):
        title = "🛠️ 다중 융합 전술 분석" if "," in tool_name else f"🛠️ {tool_name[:30]}"
        super().__init__(title=title)
        self.tool_name = tool_name
        self.category = category
        self.input_val = discord.ui.TextInput(label='분석 대상 (종목 등)')
        self.add_item(self.input_val)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        if self.category == "longtrade":
            prompt = f"가동 전술: '{self.tool_name}', 종목: '{self.input_val.value.upper()}'. 사용자가 장타(스윙/장기투자)를 치고 있다. 흔들리지 않는 펀더멘탈과 장기 모멘텀을 아주 상세하게 한국어로 브리핑해라."
        elif self.category == "daytrade":
            prompt = f"가동 전술: '{self.tool_name}', 종목: '{self.input_val.value.upper()}'. 토스(Toss) 단타 환경이다. 호가창 리스크와 단기 흐름을 구체적으로 분석하고 칼손절을 강조해라."
        else:
            prompt = f"가동 전술: '{self.tool_name}', 종목: '{self.input_val.value.upper()}'. 선택된 툴의 의미를 종합하고 한자 섞지 말고 상세하게 브리핑해라."
            
        ans = await ask_ai_async(prompt, "퀀트 맥가이버")
        await interaction.edit_original_response(embed=discord.Embed(title=f"🔥 결과: {self.input_val.value.upper()} 리포트", description=ans[:4000], color=0x95A5A6))

# ------------------------------------------
# 🗂️ 드롭다운 3종 (장타 20 / 특수 20 / 단타 20) -> 총 60종!
# ------------------------------------------
class LongTradeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 🩺 재무 엑스레이 스캔"), discord.SelectOption(label="2. ⚖️ 손익비(RR) 계산기"),
            discord.SelectOption(label="3. ❄️ 배당금 복리 머신"), discord.SelectOption(label="4. 📊 섹터 테마 스캐너"),
            discord.SelectOption(label="5. 📰 호재/악재 팩트체크"), discord.SelectOption(label="6. 🏢 라이벌 비교 스캔"),
            discord.SelectOption(label="7. 📅 어닝(실적) 충격 분석"), discord.SelectOption(label="8. 📉 구조대(물타기) 계산기"),
            discord.SelectOption(label="9. 📈 ETF 방패막이 확인"), discord.SelectOption(label="10. 💰 10대 소액 맞춤 플래너"),
            # 🌟 장타(Long) 전용 신규 10종 추가
            discord.SelectOption(label="11. 🦅 워렌 버핏 청산가치(PBR) 스캔"), discord.SelectOption(label="12. 💵 잉여현금흐름(FCF) 엑스레이"),
            discord.SelectOption(label="13. 🏰 경제적 해자(Moat) 비즈니스 판독"), discord.SelectOption(label="14. 📈 200일 장기 이동평균선 추세"),
            discord.SelectOption(label="15. ⚖️ 피터 린치 PEG 저평가 계산기"), discord.SelectOption(label="16. 🔄 경기 순환(사이클) 위치 판독"),
            discord.SelectOption(label="17. 👑 기업 독점력/가격 결정력 분석"), discord.SelectOption(label="18. 🤝 자사주 매입/주주환원 스캔"),
            discord.SelectOption(label="19. 🌍 메가트렌드(AI/친환경) 적합도"), discord.SelectOption(label="20. 🧘 3년 존버(수면 매매) 멘탈 케어")
        ]
        super().__init__(placeholder="🟢 [장타 전술] 무기고 (가치/스윙/장기투자 20종)", min_values=1, max_values=5, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        selected = ", ".join(self.values)
        await interaction.response.send_modal(QuantToolModal(tool_name=selected, category="longtrade"))

class SpecialSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 📡 세력(고래) 수급 레이더"), discord.SelectOption(label="2. 🎯 스나이퍼 타점 (RSI/MACD)"),
            discord.SelectOption(label="3. 💸 타임머신 백테스트"), discord.SelectOption(label="4. 💥 숏커버링 폭발 예측"),
            discord.SelectOption(label="5. 💣 상폐 지뢰밭 탐지기"), discord.SelectOption(label="6. 🚀 내부자(CEO) 매수 포착"),
            discord.SelectOption(label="7. 🦇 다크풀 그림자 장외 추적"), discord.SelectOption(label="8. 🔥 광기 버블 인간지표 경보"),
            discord.SelectOption(label="9. 🐺 야수의 심장 모드"), discord.SelectOption(label="10. 🕵️ VIX 폭락장 방어"),
            # 🌟 특수 작전 신규 10종 추가
            discord.SelectOption(label="11. 🩸 공매도(Short) 잔고 분석"), discord.SelectOption(label="12. 💼 월가 헤지펀드 매집 추적"),
            discord.SelectOption(label="13. 🎭 펌프앤덤프(작전주) 패턴 감지"), discord.SelectOption(label="14. 🧱 블록딜(대량매도) 폭탄 리스크"),
            discord.SelectOption(label="15. 🏛️ 정치/정책 테마 수혜 분석"), discord.SelectOption(label="16. ✂️ 스핀오프(자회사 분할) 가치"),
            discord.SelectOption(label="17. 💣 전환사채(CB) 오버행 탐지"), discord.SelectOption(label="18. ☠️ 자본잠식/흑자도산 경보"),
            discord.SelectOption(label="19. 🤝 합병/인수(M&A) 잭팟 판독"), discord.SelectOption(label="20. 🚨 하이일드 채권 스프레드 경보")
        ]
        super().__init__(placeholder="🔴 [특수 작전] 무기고 (세력추적/하이리스크 20종)", min_values=1, max_values=5, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        selected = ", ".join(self.values)
        await interaction.response.send_modal(QuantToolModal(tool_name=selected, category="special"))

class DayTradeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. ⚡ 1분봉 스캘핑 타점 판독기"), discord.SelectOption(label="2. 🚀 시초가 갭상승 스나이퍼"),
            discord.SelectOption(label="3. 💣 거래량 폭발 돌파 매매"), discord.SelectOption(label="4. 🩸 급락 눌림목 암살 전술"),
            discord.SelectOption(label="5. 🛡️ -2% 칼손절 강제 탈출"), discord.SelectOption(label="6. 🧊 VI 예측"),
            discord.SelectOption(label="7. 📉 투매 폭포수 경보"), discord.SelectOption(label="8. 🧠 뇌동매매(FOMO) 차단기"),
            discord.SelectOption(label="9. 💸 반익절 가이드"), discord.SelectOption(label="10. 🕵️ 장전 수급 스파이"),
            discord.SelectOption(label="11. ⚖️ 얇은 호가창 지뢰밭 탐지"), discord.SelectOption(label="12. 📊 VWAP 기준선 판독"),
            discord.SelectOption(label="13. 📉 쌍봉 하락 패턴 탐지"), discord.SelectOption(label="14. 🎣 밑꼬리 반등 낚시 전술"),
            discord.SelectOption(label="15. 💊 복수 매매 진정제"), discord.SelectOption(label="16. 🤖 매크로 추적"),
            discord.SelectOption(label="17. 🙏 기도 매매 팩트 폭격기"), discord.SelectOption(label="18. 🏆 거래대금 싹쓸이 스캔"),
            discord.SelectOption(label="19. ⏳ 3분 홀딩 멘탈 테스트"), discord.SelectOption(label="20. 🐺 초변동성 심박수 측정")
        ]
        super().__init__(placeholder="⚡ [단타 전술] 무기고 (토스 CQB/초단타 20종)", min_values=1, max_values=5, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        selected = ", ".join(self.values)
        await interaction.response.send_modal(QuantToolModal(tool_name=selected, category="daytrade"))

# ------------------------------------------
# 🎛️ 대시보드 UI 세팅 (5줄 테트리스 최적화)
# ------------------------------------------
class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Row 0
        self.add_item(discord.ui.Button(label="🔍 검색", style=discord.ButtonStyle.primary, custom_id="search", row=0))
        self.add_item(discord.ui.Button(label="⚖️ 타점", style=discord.ButtonStyle.success, custom_id="dca", row=0))
        self.add_item(discord.ui.Button(label="🧘 패닉룸", style=discord.ButtonStyle.danger, custom_id="pan", row=0))
        self.add_item(discord.ui.Button(label="☢️ 오메가 프로토콜 (최종 작전서)", style=discord.ButtonStyle.danger, custom_id="omega", row=0))
        # Row 1, 2, 3
        self.add_item(LongTradeSelect()) 
        self.add_item(SpecialSelect()) 
        self.add_item(DayTradeSelect()) 
        # Row 4
        self.add_item(discord.ui.Button(label="🎯 목표 설정", style=discord.ButtonStyle.success, custom_id="goal", row=4))
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

@bot.command(name="시작")
async def start_cmd(ctx):
    now_str, market_msg = get_market_status()
    embed = discord.Embed(
        title="PRO 퀀트 터미널 (V44.0 마스터 피스)", 
        description=f"📅 **현재 시각:** {now_str}\n{market_msg}\n\n🔥 **[60종 풀-아스널 장착 완료]**\n장타(20) + 특수(20) + 단타(20)가 모두 장전되었습니다. 어설픈 한자 번역체는 완전히 폐기되었으며, 10대 눈높이에 맞춘 확실한 한국어 팩트폭격만 제공합니다.", 
        color=0x0050FF
    )
    await ctx.send(embed=embed, view=DashboardView())

bot.run(DISCORD_TOKEN)
