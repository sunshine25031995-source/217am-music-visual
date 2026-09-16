import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import streamlit as st
from google import genai

APP_PASSWORD = st.secrets.get("APP_PASSWORD", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-image"

SYSTEM_PROMPT = r"""
Bạn là Creative Director cho TikTok “2:17 AM — Nơi những người không ngủ tìm thấy nhau.”

NHIỆM VỤ:
Người dùng tải lên VIDEO THAM CHIẾU. Hãy phân tích CHỈ PHẦN ÂM THANH/MUSIC của file.
Không phân tích, mô phỏng hoặc sao chép visual, nhân vật, bối cảnh, caption, typography hay câu chuyện cụ thể từ video.
Chỉ lấy cảm xúc và tinh thần mà phần nhạc truyền tải.

Sau khi phân tích nhạc, tạo một VISUAL HOÀN TOÀN MỚI cho thương hiệu 2:17 AM.

VISUAL DNA:
- BẮT BUỘC có một cô gái làm nhân vật chính.
- Ưu tiên bóng lưng/quay lưng về camera.
- Faceless, không lộ rõ khuôn mặt.
- Cô gái ở trong không gian mở, rộng, có chiều sâu.
- Không mặc định phòng ngủ, phòng kín, xe hơi hoặc không gian hẹp.
- Tự chọn bối cảnh phù hợp với cảm xúc của bài nhạc: phố đêm, biển, con đường vắng, sân ga, cây cầu, rooftop, bãi đỗ xe, cánh đồng, rừng, thành phố, mưa, hoàng hôn, bình minh...
- Nhân vật thường đứng hoặc bước đi một mình.
- Cô gái không chiếm quá nhiều khung hình.
- Không tạo dáng thời trang.
- Không gian xung quanh phải góp phần kể câu chuyện.
- Ưu tiên cảm giác cô gái nhỏ bé giữa một thế giới rất rộng.
- Visual phải giống một frame trong phim, không phải poster.

STYLE:
Photorealistic, cinematic, melancholic, emotional, realistic lighting,
subtle film grain, natural skin and fabric texture, shallow depth of field,
dark blue, charcoal, muted tones, warm amber when appropriate,
premium music-video aesthetic, vertical 9:16.

KHÔNG:
- Fantasy
- Stock photo
- Artificial CGI look
- Fashion editorial pose
- Quá sến
- Text/caption/logo/typography/watermark trên ảnh

CAPTION:
Viết RIÊNG bên ngoài ảnh.
Tiếng Việt, NGẮN NHƯNG THẤM.
Chỉ 1–3 câu.
Đời, tự nhiên, có insight tâm lý.
Không sáo rỗng, không cố văn chương, không kể lể.
Không giải thích dài.
Câu cuối nên có dư âm và khiến người đọc nghĩ: “Ừ, chính là cảm giác đó.”

OUTPUT:
Trả về JSON hợp lệ với đúng các key:
{
  "music_analysis": {
    "mood": "...",
    "emotion": "...",
    "psychological_state": "...",
    "emotional_peak": "..."
  },
  "visual_concept": {
    "setting": "...",
    "time": "...",
    "lighting": "...",
    "girl_action": "...",
    "camera": "...",
    "visual_emotion": "..."
  },
  "image_prompt": "...",
  "caption": "..."
}

image_prompt phải là prompt tiếng Anh hoàn chỉnh để generate ảnh 9:16 và phải tự chứa đầy đủ Visual DNA.
caption không được đặt trong image_prompt.
"""

def extract_audio(video_bytes: bytes, suffix: str) -> str:
    src = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    src.write(video_bytes)
    src.close()

    out_path = src.name + ".mp3"
    cmd = [
        "ffmpeg", "-y", "-i", src.name,
        "-vn", "-ac", "2", "-ar", "44100", "-b:a", "192k",
        out_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        os.remove(src.name)
    except OSError:
        pass

    if result.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("Không thể tách audio từ video. Hãy thử một file MP4/MOV khác có âm thanh.")
    return out_path

def wait_for_active(client, uploaded_file, timeout=180):
    start = time.time()
    current = uploaded_file
    while True:
        state = getattr(current, "state", None)
        state_name = getattr(state, "name", str(state))
        if state_name == "ACTIVE":
            return current
        if state_name in ("FAILED", "ERROR"):
            raise RuntimeError(f"Gemini không xử lý được audio (state={state_name}).")
        if time.time() - start > timeout:
            raise TimeoutError("Gemini xử lý audio quá lâu. Hãy thử lại với file ngắn hơn.")
        time.sleep(2)
        current = client.files.get(name=current.name)

def parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "", 1).strip()
    return json.loads(text)

st.set_page_config(
    page_title="2:17 AM — Music → Visual",
    page_icon="🌙",
    layout="centered"
)

st.markdown("""
<style>
.block-container {max-width: 900px; padding-top: 2rem;}
h1 {letter-spacing: -0.03em;}
.small {opacity: .7; font-size: .9rem;}
.card {padding: 1rem 1.1rem; border: 1px solid rgba(128,128,128,.22);
       border-radius: 14px; margin: .7rem 0;}
</style>
""", unsafe_allow_html=True)

st.title("🌙 2:17 AM")
st.caption("Music → Visual Generator")
st.markdown('<div class="small">Phân tích cảm xúc từ phần nhạc → Visual concept → Image Prompt → Caption ngắn nhưng thấm.</div>', unsafe_allow_html=True)

if not APP_PASSWORD or not GEMINI_API_KEY:
    st.error("App chưa được cấu hình API key/password. Hãy thêm GEMINI_API_KEY và APP_PASSWORD trong Streamlit Secrets.")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.text_input("🔐 Mật khẩu", type="password")
    if st.button("Vào tool", type="primary", use_container_width=True):
        if password == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Mật khẩu không đúng.")
    st.stop()

uploaded = st.file_uploader(
    "🎵 Upload video/đoạn nhạc tham chiếu",
    type=["mp4", "mov", "m4v", "webm"],
    help="MVP sẽ tách phần audio trước khi gửi lên Gemini để giảm ảnh hưởng của visual tham chiếu."
)

if uploaded:
    st.video(uploaded)
    if st.button("🎧 PHÂN TÍCH NHẠC", type="primary", use_container_width=True):
        audio_path = None
        try:
            if uploaded.size > 2 * 1024 * 1024 * 1024:
                st.error("File vượt 2GB. Hãy dùng file nhỏ hơn.")
                st.stop()

            with st.status("Đang xử lý...", expanded=True) as status:
                st.write("1/3 — Tách audio khỏi video...")
                audio_path = extract_audio(uploaded.getvalue(), Path(uploaded.name).suffix.lower())

                st.write("2/3 — Gửi audio lên Gemini...")
                client = genai.Client(api_key=GEMINI_API_KEY)
                audio_file = client.files.upload(file=audio_path)

                st.write("3/3 — Phân tích cảm xúc và tạo visual...")
                audio_file = wait_for_active(client, audio_file)

                response = client.models.generate_content(
                    model=MODEL,
                    contents=[audio_file, SYSTEM_PROMPT],
                    config={
                        "response_mime_type": "application/json",
                        "temperature": 0.9,
                    },
                )
                data = parse_json(response.text)
                status.update(label="Hoàn tất ✨", state="complete")

            st.session_state.result = data

        except json.JSONDecodeError:
            st.error("Gemini trả về định dạng không hợp lệ. Hãy bấm phân tích lại.")
        except Exception as e:
            st.error(f"Lỗi: {e}")
        finally:
            if audio_path:
                try:
                    os.remove(audio_path)
                except OSError:
                    pass

if "result" in st.session_state:
    d = st.session_state.result
    ma = d["music_analysis"]
    vc = d["visual_concept"]

    st.divider()
    st.subheader("🎵 1. PHÂN TÍCH NHẠC")
    st.markdown(f"**Mood**  \n{ma['mood']}")
    st.markdown(f"**Cảm xúc chủ đạo**  \n{ma['emotion']}")
    st.markdown(f"**Trạng thái tâm lý**  \n{ma['psychological_state']}")
    st.markdown(f"**Điểm cảm xúc mạnh nhất**  \n{ma['emotional_peak']}")

    st.divider()
    st.subheader("🎬 2. Ý TƯỞNG VISUAL")
    st.markdown(f"**Bối cảnh:** {vc['setting']}")
    st.markdown(f"**Thời gian:** {vc['time']}")
    st.markdown(f"**Ánh sáng:** {vc['lighting']}")
    st.markdown(f"**Cô gái:** {vc['girl_action']}")
    st.markdown(f"**Góc máy:** {vc['camera']}")
    st.markdown(f"**Cảm xúc hình ảnh:** {vc['visual_emotion']}")

    st.divider()
    st.subheader("🖼️ 3. ENGLISH IMAGE PROMPT")
    st.text_area("Copy prompt", d["image_prompt"], height=330, label_visibility="collapsed")

    st.divider()
    st.subheader("✍️ 4. CAPTION")
    st.markdown(f"> {d['caption']}")
    st.text_area("Copy caption", d["caption"], height=110, label_visibility="collapsed")

    all_text = f"""2:17 AM — MUSIC ANALYSIS

Mood: {ma['mood']}
Emotion: {ma['emotion']}
Psychological state: {ma['psychological_state']}
Emotional peak: {ma['emotional_peak']}

VISUAL CONCEPT
Setting: {vc['setting']}
Time: {vc['time']}
Lighting: {vc['lighting']}
Girl: {vc['girl_action']}
Camera: {vc['camera']}
Visual emotion: {vc['visual_emotion']}

IMAGE PROMPT
{d['image_prompt']}

CAPTION
{d['caption']}
"""
    st.download_button(
        "⬇️ TẢI KẾT QUẢ .TXT",
        data=all_text,
        file_name="217am_result.txt",
        mime="text/plain",
        use_container_width=True
    )
