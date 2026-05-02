import random
import time
import streamlit as st
import streamlit.components.v1 as components
import difflib
from audio_recorder_streamlit import audio_recorder
import io
from gtts import gTTS
import speech_recognition as sr

from passages import ALL_PASSAGES

PASSAGES_PER_CYCLE = 2  # 2 passages × 3 questions = 6 questions


def make_tts_audio(text: str) -> bytes | None:
    for _ in range(2):
        try:
            tts = gTTS(text=text, lang="en")
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            return fp.read()
        except Exception:
            pass
    return None


def audio_duration_estimate(text: str) -> float:
    return len(text.split()) * 0.42 + 0.8


def score_answer(user_text: str, answers: list[str]) -> int:
    if not user_text.strip():
        return 0
    user_words = set(user_text.lower().split())
    best = 0
    for ans in answers:
        ans_words = set(ans.lower().split())
        if ans_words:
            overlap = len(user_words & ans_words) / len(ans_words)
            best = max(best, int(overlap * 100))
        ratio = difflib.SequenceMatcher(None, ans.lower(), user_text.lower()).ratio()
        best = max(best, int(ratio * 100))
    return best


def reset_cycle():
    selected = random.sample(ALL_PASSAGES, min(PASSAGES_PER_CYCLE, len(ALL_PASSAGES)))
    st.session_state.update(
        page="test",
        passages=selected,
        p_index=0,
        q_index=0,
        phase="passage_playing",
        tts_audio=None,
        tts_for=None,
        recorder_started=False,
        recorded_audio=None,
        user_text="",
        score=0,
        do_stop_recording=False,
        playback_start=None,
        playback_wait=0.0,
        recording_start=None,
        results=[],
    )


def current_passage():
    return st.session_state.passages[st.session_state.p_index]


def _total_q_idx():
    return st.session_state.p_index * 3 + st.session_state.q_index


def record_result(score: int, user_text: str):
    passage = current_passage()
    q_idx = st.session_state.q_index
    if len(st.session_state.results) == _total_q_idx():
        st.session_state.results.append({
            "passage": passage["passage"],
            "question": passage["questions"][q_idx],
            "expected": passage["answers"][q_idx],
            "user_text": user_text,
            "score": score,
        })


def go_next():
    q = st.session_state.q_index
    p = st.session_state.p_index
    next_phase = "q_playing"
    if q < 2:
        st.session_state.q_index = q + 1
        next_phase = "q_playing"
    elif p < len(st.session_state.passages) - 1:
        st.session_state.p_index = p + 1
        st.session_state.q_index = 0
        next_phase = "passage_playing"
    else:
        st.session_state.page = "summary"
        return
    st.session_state.phase = next_phase
    st.session_state.tts_audio = None
    st.session_state.tts_for = None
    st.session_state.recorder_started = False
    st.session_state.recorded_audio = None
    st.session_state.user_text = ""
    st.session_state.score = 0
    st.session_state.do_stop_recording = False
    st.session_state.playback_start = None
    st.session_state.playback_wait = 0.0
    st.session_state.recording_start = None


def retry_question():
    st.session_state.phase = "q_playing"
    st.session_state.tts_audio = None
    st.session_state.tts_for = None
    st.session_state.recorder_started = False
    st.session_state.recorded_audio = None
    st.session_state.user_text = ""
    st.session_state.score = 0
    st.session_state.do_stop_recording = False
    st.session_state.playback_start = None
    st.session_state.playback_wait = 0.0
    st.session_state.recording_start = None
    total_q = _total_q_idx()
    if len(st.session_state.results) > total_q:
        st.session_state.results = st.session_state.results[:total_q]


@st.fragment(run_every=0.5)
def playback_countdown():
    phase = st.session_state.get("phase")
    if phase not in ("passage_playing", "q_playing"):
        return
    if not st.session_state.get("playback_start"):
        return
    elapsed = time.time() - st.session_state.playback_start
    remaining = st.session_state.playback_wait - elapsed
    if remaining <= 0:
        st.session_state.playback_start = None
        if phase == "passage_playing":
            st.session_state.phase = "q_playing"
        else:
            st.session_state.phase = "q_recording"
            st.session_state.recorder_started = False
            st.session_state.recording_start = time.time()
        st.rerun(scope="app")
    else:
        st.caption(f"⏱️ 残り {max(1, int(remaining))} 秒...")


@st.fragment(run_every=1)
def recording_timer():
    if st.session_state.get("phase") != "q_recording":
        return
    start = st.session_state.get("recording_start")
    if start is None:
        return
    elapsed = time.time() - start
    remaining = max(0, 10 - int(elapsed))
    if remaining > 0:
        st.progress(remaining / 10, text=f"⏳ {remaining} 秒以内に話し始めてください")
    else:
        if not st.session_state.get("recorded_audio"):
            record_result(0, "")
            st.session_state.phase = "q_result"
            st.rerun(scope="app")


# ── ホームページ ───────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("Answer Questions About a Passage")
    st.caption("英語のパッセージを聞いて、3つの質問に短く答える練習です。（VERSANT Part D）")

    st.info(
        "**テストの流れ**\n\n"
        "1. 短い英語のパッセージ（50〜150語）を聞きます\n"
        "2. 3つの質問を聞いて、それぞれ短い英語で答えます\n"
        "3. 2パッセージ × 3問 = 全6問\n\n"
        "**コツ:** パッセージの内容をしっかり聞き、質問への答えは短く明確に話しましょう。"
    )

    if st.button("スタート", type="primary"):
        reset_cycle()
        st.rerun()

    st.stop()

# ── サマリーページ ─────────────────────────────────────────────────
if st.session_state.get("page") == "summary":
    results = st.session_state.get("results", [])
    avg = sum(r["score"] for r in results) / len(results) if results else 0

    st.title("お疲れ様でした！")

    col_avg, col_hi, col_lo = st.columns(3)
    with col_avg:
        st.metric("平均スコア", f"{avg:.1f} / 100")
    with col_hi:
        best = max(results, key=lambda r: r["score"]) if results else None
        st.metric("最高スコア", f"{best['score']} / 100" if best else "-")
    with col_lo:
        worst = min(results, key=lambda r: r["score"]) if results else None
        st.metric("最低スコア", f"{worst['score']} / 100" if worst else "-")

    st.divider()
    st.subheader("全問結果")
    for i, r in enumerate(results, 1):
        score = r["score"]
        color = "🟢" if score > 70 else ("🟡" if score > 40 else "🔴")
        with st.expander(f"{color} Q{i}. {r['question']}　→　**{score} 点**"):
            st.write(f"**質問:** {r['question']}")
            st.write(f"**期待される回答例:** {r['expected'][0]}")
            st.write(f"**あなたの回答:** {r['user_text'] if r['user_text'] else '（回答なし）'}")
            st.progress(score / 100)

    st.divider()
    if st.button("もう一度（シャッフル）", type="primary"):
        reset_cycle()
        st.rerun()
    if st.button("トップに戻る"):
        st.session_state.page = "home"
        st.rerun()
    st.stop()

# ── サイドバー ─────────────────────────────────────────────────────
with st.sidebar:
    st.title("設定")
    p_idx = st.session_state.get("p_index", 0)
    q_idx = st.session_state.get("q_index", 0)
    total_q = p_idx * 3 + q_idx + 1
    st.write(f"**進捗:** {total_q} / 6 問")
    if st.button("トップに戻る"):
        st.session_state.page = "home"
        st.rerun()

# デフォルト値の保証
defaults = dict(
    passages=[],
    p_index=0,
    q_index=0,
    phase="passage_playing",
    tts_audio=None,
    tts_for=None,
    recorder_started=False,
    recorded_audio=None,
    user_text="",
    score=0,
    do_stop_recording=False,
    playback_start=None,
    playback_wait=0.0,
    recording_start=None,
    results=[],
)
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.passages:
    reset_cycle()

passage = current_passage()
p_idx = st.session_state.p_index
q_idx = st.session_state.q_index
total_q_num = p_idx * 3 + q_idx + 1

st.title("Answer Questions About a Passage")
st.subheader(f"Passage {p_idx + 1} / {PASSAGES_PER_CYCLE}　|　Question {total_q_num} / 6")

# ══════════════════════════════════════════════════════
# Phase: passage_playing
# ══════════════════════════════════════════════════════
if st.session_state.phase == "passage_playing":
    tts_key = f"passage_{p_idx}"
    if st.session_state.tts_for != tts_key:
        with st.spinner("音声を生成中..."):
            audio = make_tts_audio(passage["passage"])
        if audio is None:
            st.error("音声の生成に失敗しました。")
            col_r, col_s = st.columns(2)
            with col_r:
                if st.button("🔄 リトライ"):
                    st.rerun()
            with col_s:
                if st.button("⏭️ スキップ"):
                    st.session_state.phase = "q_playing"
                    st.rerun()
            st.stop()
        st.session_state.tts_audio = audio
        st.session_state.tts_for = tts_key
        st.session_state.playback_start = time.time()
        st.session_state.playback_wait = audio_duration_estimate(passage["passage"]) + 1.5

    st.info("🎧 パッセージを聞いてください。内容をよく覚えましょう。")
    st.audio(st.session_state.tts_audio, format="audio/mp3", autoplay=True)
    playback_countdown()

# ══════════════════════════════════════════════════════
# Phase: q_playing
# ══════════════════════════════════════════════════════
elif st.session_state.phase == "q_playing":
    question = passage["questions"][q_idx]
    tts_key = f"q_{p_idx}_{q_idx}"
    if st.session_state.tts_for != tts_key:
        with st.spinner("質問の音声を生成中..."):
            audio = make_tts_audio(question)
        if audio is None:
            st.error("音声の生成に失敗しました。")
            if st.button("🔄 リトライ"):
                st.rerun()
            st.stop()
        st.session_state.tts_audio = audio
        st.session_state.tts_for = tts_key
        st.session_state.playback_start = time.time()
        st.session_state.playback_wait = audio_duration_estimate(question) + 1.0

    st.info(f"🎧 質問 {q_idx + 1} を聞いてください。")
    st.audio(st.session_state.tts_audio, format="audio/mp3", autoplay=True)
    playback_countdown()

# ══════════════════════════════════════════════════════
# Phase: q_recording
# ══════════════════════════════════════════════════════
elif st.session_state.phase == "q_recording":
    question = passage["questions"][q_idx]
    st.error("🔴 **録音中です。質問に短く英語で答えてください。**")
    st.write(f"**質問 {q_idx + 1}:** {question}")

    recording_timer()

    col_stop, col_replay = st.columns([1, 1])
    with col_stop:
        if st.button("✅ 回答完了", type="primary"):
            st.session_state.do_stop_recording = True
            st.rerun()
    with col_replay:
        if st.button("🔊 質問をもう一度聞く"):
            st.session_state.phase = "q_playing"
            st.session_state.tts_audio = None
            st.session_state.tts_for = None
            st.session_state.playback_start = None
            st.session_state.recorder_started = False
            st.session_state.recording_start = None
            st.rerun()

    if st.session_state.do_stop_recording:
        st.session_state.do_stop_recording = False
        components.html("""
        <script>
        setTimeout(function() {
            var frames = window.parent.document.querySelectorAll('iframe');
            for (var i = 0; i < frames.length; i++) {
                try {
                    var btn = frames[i].contentDocument.querySelector('button[aria-label="Record"]');
                    if (btn) { btn.click(); break; }
                } catch(e) {}
            }
        }, 300);
        </script>
        """, height=0)

    auto_start = not st.session_state.recorder_started
    audio_bytes = audio_recorder(
        text="",
        auto_start=auto_start,
        pause_threshold=4.0,
        sample_rate=44_100,
        key="answer_recorder",
    )
    st.session_state.recorder_started = True

    if audio_bytes:
        with st.spinner("音声を解析中..."):
            recognizer = sr.Recognizer()
            try:
                with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
                    audio_data = recognizer.record(source)
                user_text = recognizer.recognize_google(audio_data)
            except sr.UnknownValueError:
                user_text = ""
            except sr.RequestError:
                user_text = ""

        answers = passage["answers"][q_idx]
        score = score_answer(user_text, answers)
        st.session_state.user_text = user_text
        st.session_state.score = score
        st.session_state.recorded_audio = audio_bytes

        record_result(score, user_text)
        st.session_state.phase = "q_result"
        st.rerun()

# ══════════════════════════════════════════════════════
# Phase: q_result
# ══════════════════════════════════════════════════════
elif st.session_state.phase == "q_result":
    question = passage["questions"][q_idx]
    answers = passage["answers"][q_idx]
    score = st.session_state.score

    st.metric("スコア", f"{score} / 100")

    if score > 70:
        st.success("よくできました！")
    elif score > 40:
        st.warning("惜しい！キーワードが一部合っています。")
    else:
        st.error("次の質問を頑張りましょう。")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**質問:** {question}")
        st.success(f"**回答例:** {answers[0]}")
    with col2:
        user_t = st.session_state.user_text
        st.error(f"**あなたの回答:** {user_t if user_t else '（認識できませんでした）'}")
        if st.session_state.recorded_audio:
            st.write("▶️ あなたの録音")
            st.audio(st.session_state.recorded_audio, format="audio/wav")

    st.divider()
    col_retry, col_next = st.columns(2)
    with col_retry:
        if st.button("この質問をやり直す"):
            retry_question()
            st.rerun()
    with col_next:
        is_last = (q_idx == 2 and p_idx == len(st.session_state.passages) - 1)
        next_label = "結果を見る" if is_last else "次の質問 ➡"
        if st.button(next_label, type="primary"):
            go_next()
            st.rerun()
