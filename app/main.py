import base64
import datetime
import urllib.parse
from pathlib import Path
from typing import Union, List, Dict, Any

import httpx
from fastapi import FastAPI, Response, Request, Cookie, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from youtubesearchpython import (
    VideosSearch, ChannelsSearch, Video, Channel, Playlist, Comments, Suggestions
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

EDU_STREAM_API = "https://siawaseok.duckdns.org/api/stream/"
YTDL_STREAM_API = "https://yudlp-ygug.onrender.com/stream/"
M3U8_STREAM_API = "https://yudlp-ygug.onrender.com/m3u8/"
BBS_API = "https://server-bbs.vercel.app"

client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0),
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36'}
)

async def get_base64_thumbnail(url: str) -> str:
    if not url or url == "Load Failed":
        return ""
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            encoded_body = base64.b64encode(resp.content).decode("utf-8")
            return f"data:{content_type};base64,{encoded_body}"
    except:
        pass
    return ""

def format_duration(seconds):
    if not seconds: return "0:00"
    try:
        return str(datetime.timedelta(seconds=int(seconds)))
    except:
        return "0:00"

async def get_video_data(videoid: str):
    video_info = Video.getInfo(videoid)
    if not video_info:
        return None, []

    author_icon_url = video_info.get('channel', {}).get('thumbnails', [{}])[-1].get('url', '')
    author_icon_b64 = await get_base64_thumbnail(author_icon_url)

    video_details = {
        'title': video_info.get('title', 'N/A'),
        'description': video_info.get('description', ''),
        'author': video_info.get('channel', {}).get('name', 'N/A'),
        'author_id': video_info.get('channel', {}).get('id', ''),
        'author_icon': author_icon_b64,
        'view_count': video_info.get('viewCount', {}).get('text', '0'),
        'like_count': str(video_info.get('likes', '0')),
        'subscribers_count': video_info.get('channel', {}).get('subscribers', {}).get('simpleText', 'N/A'),
        'published_text': video_info.get('publishDate', 'N/A'),
        'length_text': format_duration(video_info.get('duration', {}).get('secondsText', 0))
    }

    related = []
    suggestions = video_info.get('suggestions', [])[:12]
    for item in suggestions:
        if item.get('type') == 'video':
            thumb_url = f"https://i.ytimg.com/vi/{item.get('id')}/mqdefault.jpg"
            related.append({
                "id": item.get('id'),
                "title": item.get('title'),
                "author": item.get('channel', {}).get('name'),
                "length": item.get('duration', {}).get('text', '0:00'),
                "thumbnail": await get_base64_thumbnail(thumb_url)
            })
            
    return video_details, related

@app.get('/', response_class=HTMLResponse)
async def home(request: Request, yuzu_access_granted: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if yuzu_access_granted != "True":
        return RedirectResponse(url="/gate")
    
    search_obj = VideosSearch("Music", limit=20)
    results = search_obj.result().get('result', [])
    for item in results:
        thumb_url = item.get('thumbnails', [{}])[0].get('url', '')
        item['thumbnail_b64'] = await get_base64_thumbnail(thumb_url)

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "proxy": proxy,
        "results": results,
        "word": ""
    })

@app.get('/gate', response_class=HTMLResponse)
async def access_gate_get(request: Request):
    return templates.TemplateResponse("access_gate.html", {
        "request": request,
        "message": "アクセスコードを入力してください。"
    })

@app.post('/gate')
async def access_gate_post(request: Request, access_code: str = Form(...)):
    if access_code == "yuzu":
        response = RedirectResponse(url="/", status_code=302)
        expires_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        response.set_cookie(
            key="yuzu_access_granted", 
            value="True", 
            expires=expires_time.strftime("%a, %d-%b-%Y %H:%M:%S GMT"), 
            httponly=True,
            samesite="lax"
        )
        return response
    else:
        return templates.TemplateResponse("access_gate.html", {
            "request": request,
            "message": "無効なアクセスコードです。",
            "error": True
        }, status_code=401)

@app.get('/watch', response_class=HTMLResponse)
async def watch(v: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    video_details, related = await get_video_data(v)
    high_res_url = ""
    try:
        m3u8_resp = await client.get(f"{M3U8_STREAM_API}{v}")
        if m3u8_resp.status_code == 200:
            m3u8_data = m3u8_resp.json()
            formats = m3u8_data.get('m3u8_formats', [])
            if formats:
                high_res_url = sorted(formats, key=lambda x: int(x.get('resolution', '0').split('x')[-1] if 'x' in x.get('resolution', '') else 0))[-1]['url']
    except:
        pass

    return templates.TemplateResponse('video.html', {
        "request": request,
        "videoid": v,
        "video": video_details,
        "high_quality_url": high_res_url,
        "recommended_videos": related,
        "proxy": proxy
    })

@app.get("/search", response_class=HTMLResponse)
async def search(q: str, request: Request, page: int = 1, proxy: Union[str, None] = Cookie(None)):
    search_obj = VideosSearch(q, limit=15, offset=(page-1)*15)
    results = search_obj.result().get('result', [])
    for item in results:
        thumb_url = item.get('thumbnails', [{}])[0].get('url', '')
        item['thumbnail_b64'] = await get_base64_thumbnail(thumb_url)

    return templates.TemplateResponse("search.html", {
        "request": request,
        "results": results,
        "word": q,
        "next": f"/search?q={q}&page={page + 1}",
        "proxy": proxy
    })

@app.get("/channel/{channelid}", response_class=HTMLResponse)
async def channel(channelid: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    ch_obj = Channel.get(channelid)
    icon_b64 = await get_base64_thumbnail(ch_obj.get('thumbnails', [{}])[-1].get('url', ''))
    banner_url = ch_obj.get('banners', [{}])[-1].get('url', '')
    
    videos = ch_obj.get('uploads', {}).get('videos', [])[:20]
    for v in videos:
        v['thumbnail_b64'] = await get_base64_thumbnail(v.get('thumbnails', [{}])[0].get('url', ''))

    return templates.TemplateResponse("channel.html", {
        "request": request,
        "channel_name": ch_obj.get('title'),
        "channel_icon": icon_b64,
        "channel_profile": ch_obj.get('description', ''),
        "cover_img_url": banner_url,
        "results": videos,
        "subscribers_count": ch_obj.get('subscribers', {}).get('simpleText', 'N/A'),
        "proxy": proxy
    })

@app.get("/api/bbs/posts")
async def get_bbs_posts():
    resp = await client.get(f"{BBS_API}/posts")
    return resp.json()

@app.post("/api/bbs/post")
async def post_new_message(request: Request):
    data = await request.json()
    client_ip = request.headers.get("x-forwarded-for", "unknown").split(',')[0].strip()
    resp = await client.post(f"{BBS_API}/post", json=data, headers={"X-Original-Client-IP": client_ip})
    return resp.json()

@app.get("/suggest")
async def suggest(keyword: str):
    try:
        suggestions_obj = Suggestions(language='ja', region='JP')
        suggestions = suggestions_obj.get(keyword)
        return suggestions.get('result', [])
    except:
        return []

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()
