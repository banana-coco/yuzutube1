import json
import time
import requests
import datetime
import urllib.parse
from pathlib import Path 
from typing import Union, List, Dict, Any
import asyncio 
import concurrent.futures
from fastapi import FastAPI, Response, Request, Cookie, Form 
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool 

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates")) 

class APITimeoutError(Exception): pass

def getRandomUserAgent(): 
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36'}

def isJSON(json_str):
    try: 
        json.loads(json_str)
        return True
    except (json.JSONDecodeError, TypeError): 
        return False

max_time = 10.0
max_api_wait_time = (3.0, 8.0)
failed = "取得失敗"

PROXY_URL = "http://ytproxy-siawaseok.duckdns.org:3007"
PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL,
}

EDU_STREAM_API_BASE_URL = "https://siawaseok.duckdns.org/api/stream/" 
EDU_VIDEO_API_BASE_URL = "https://api-five-zeta-55.vercel.app/api/video/"
STREAM_YTDL_API_BASE_URL = "https://yudlp-ygug.onrender.com/stream/" 
SHORT_STREAM_API_BASE_URL = "https://yt-dl-kappa.vercel.app/short/"
BBS_EXTERNAL_API_BASE_URL = "https://server-bbs.vercel.app"

invidious_api_data = {
    'video': [], 
    'playlist': [
        'https://invidious.lunivers.trade/',
        'https://invidious.ducks.party/',
        'https://super8.absturztau.be/',
        'https://invidious.nikkosphere.com/',
        'https://yt.omada.cafe/',
        'https://iv.melmac.space/',
        'https://iv.duti.dev/',
    ], 
    'search': [
        'https://api-five-zeta-55.vercel.app/',
    ], 
    'channel': [
        'https://invidious.lunivers.trade/',
        'https://invid-api.poketube.fun/',
        'https://invidious.ducks.party/',
        'https://super8.absturztau.be/',
        'https://invidious.nikkosphere.com/',
        'https://yt.omada.cafe/',
        'https://iv.melmac.space/',
        'https://iv.duti.dev/',
    ], 
    'comments': [
        'https://invidious.lunivers.trade/',
        'https://invidious.ducks.party/',
        'https://super8.absturztau.be/',
        'https://invidious.nikkosphere.com/',
        'https://yt.omada.cafe/',
        'https://iv.duti.dev/',
        'https://iv.melmac.space/',
    ]
}

class InvidiousAPI:
    def __init__(self):
        self.all = invidious_api_data
        self.video = list(self.all['video'])
        self.playlist = list(self.all['playlist'])
        self.search = list(self.all['search'])
        self.channel = list(self.all['channel'])
        self.comments = list(self.all['comments'])

invidious_api = InvidiousAPI()

def requestAPI(path, api_urls):
    apis_to_try = api_urls
    if not apis_to_try:
        raise APITimeoutError("API設定なし")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(apis_to_try)) as executor:
        future_to_api = {
            executor.submit(
                requests.get, 
                api + 'api/v1' + path, 
                headers=getRandomUserAgent(), 
                timeout=max_api_wait_time,
                proxies=PROXIES,
                verify=False
            ): api for api in apis_to_try
        }
        for future in concurrent.futures.as_completed(future_to_api, timeout=max_time):
            try:
                res = future.result()
                if res.status_code == requests.codes.ok and isJSON(res.text):
                    return res.text
            except:
                continue
    raise APITimeoutError("API応答なし")

def getEduKey():
    try:
        res = requests.get("https://apis.kahoot.it/media-api/youtube/key", headers=getRandomUserAgent(), timeout=max_api_wait_time, proxies=PROXIES, verify=False)
        return json.loads(res.text).get("key")
    except:
        return None

def formatSearchData(data_dict):
    t = data_dict.get("type")
    if t == "video": 
        return {
            "type": "video", 
            "title": data_dict.get("title", failed), 
            "id": data_dict.get("videoId", failed), 
            "author": data_dict.get("author", failed), 
            "published": data_dict.get("publishedText", failed), 
            "length": str(datetime.timedelta(seconds=data_dict.get("lengthSeconds", 0))), 
            "view_count_text": data_dict.get("viewCountText", failed)
        }
    elif t == "playlist": 
        return {
            "type": "playlist", 
            "title": data_dict.get("title", failed), 
            "id": data_dict.get('playlistId', failed), 
            "thumbnail": data_dict.get("playlistThumbnail", failed), 
            "count": data_dict.get("videoCount", failed)
        }
    elif t == "channel":
        thumbs = data_dict.get('authorThumbnails', [])
        thumbnail = thumbs[-1].get('url', failed) if thumbs else failed
        return {"type": "channel", "author": data_dict.get("author", failed), "id": data_dict.get("authorId", failed), "thumbnail": thumbnail}
    return {"type": "unknown"}

def fetch_video_data_from_edu_api(videoid: str):
    target_url = f"{EDU_VIDEO_API_BASE_URL}{urllib.parse.quote(videoid)}"
    res = requests.get(
        target_url, 
        headers=getRandomUserAgent(), 
        timeout=max_api_wait_time,
        proxies=PROXIES,
        verify=False
    )
    res.raise_for_status()
    return res.json()

def format_related_video(related_data: dict) -> dict:
    vid = related_data.get("videoId") or related_data.get("id", failed)
    is_p = "playlistId" in related_data and related_data["playlistId"] != vid
    return {
        "type": "playlist" if is_p else "video",
        "id": related_data.get('playlistId') if is_p else vid,
        "video_id": vid,
        "title": related_data.get("title", failed), 
        "author": related_data.get("author") or related_data.get("channel", failed),
        "author_id": related_data.get("authorId") or related_data.get("channelId", failed),
        "length_text": related_data.get("lengthText", ""),
        "view_count_text": related_data.get("viewCountText", ""),
        "published_text": related_data.get("publishedText", ""),
        "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/sddefault.jpg"
    }

async def getVideoData(videoid):
    try:
        t = await run_in_threadpool(fetch_video_data_from_edu_api, videoid)
    except Exception as e:
        raise APITimeoutError(f"API Error: {e}")

    if t.get("playability_status", {}).get("status") == "LOGIN_REQUIRED":
        raise APITimeoutError("Bot検知によりアクセスが制限されています")

    basic = t.get("basic_info") or {}
    author = t.get("author") or {}
    
    video_details = {
        'video_urls': [], 
        'description_html': t.get("descriptionHtml") or t.get("description") or "説明なし", 
        'title': t.get("title") or basic.get("title") or failed,
        'author_id': author.get("id") or basic.get("channelId") or failed, 
        'author': author.get("name") or basic.get("channel") or failed, 
        'author_thumbnails_url': author.get("thumbnail") or failed, 
        'view_count': t.get("viewCount") or basic.get("view_count") or "0", 
        'like_count': t.get("likeCount") or basic.get("like_count") or "0", 
        'subscribers_count': author.get("subscribers") or "不明",
        'published_text': t.get("publishedText") or t.get("relativeDate") or "",
        "length_text": t.get("lengthText") or "" 
    }
    related = [format_related_video(i) for i in t.get('related', []) if isinstance(i, dict)]
    return [video_details, related]

async def getSearchData(q, page):
    text = await run_in_threadpool(requestAPI, f"/search?q={urllib.parse.quote(q)}&page={page}&hl=jp", invidious_api.search)
    return [formatSearchData(d) for d in json.loads(text)]

async def getTrendingData(region: str):
    text = await run_in_threadpool(requestAPI, f"/trending?region={region}&hl=jp", invidious_api.search)
    return [formatSearchData(d) for d in json.loads(text) if d.get("type") == "video"]

async def getChannelData(channelid):
    try:
        text = await run_in_threadpool(requestAPI, f"/channels/{urllib.parse.quote(channelid)}", invidious_api.channel)
        t = json.loads(text)
    except:
        t = {}
    videos = t.get('latestVideos') or t.get('latestvideo') or []
    icon = t.get("authorThumbnails", [{}])[-1].get("url", failed)
    banner = urllib.parse.quote(t.get('authorBanners', [{}])[0].get("url", ""), safe="-_.~/:") if t.get('authorBanners') else ""
    results = [{"type": "video", "title": i.get("title", failed), "id": i.get("videoId", failed), "author": t.get("author", failed), "published": i.get("publishedText", failed), "view_count_text": i.get('viewCountText', failed), "length_str": str(datetime.timedelta(seconds=i.get("lengthSeconds", 0)))} for i in videos]
    info = {"channel_name": t.get("author", "不明"), "channel_icon": icon, "channel_profile": t.get("descriptionHtml", ""), "author_banner": banner, "subscribers_count": t.get("subCount", "0"), "tags": t.get("tags", [])}
    return [results, info]

async def getPlaylistData(listid, page):
    text = await run_in_threadpool(requestAPI, f"/playlists/{urllib.parse.quote(listid)}?page={urllib.parse.quote(str(page))}", invidious_api.playlist)
    return [{"title": v["title"], "id": v["videoId"], "authorId": v["authorId"], "author": v["author"], "type": "video"} for v in json.loads(text).get("videos", [])]

async def getCommentsData(videoid):
    try:
        text = await run_in_threadpool(requestAPI, f"/comments/{urllib.parse.quote(videoid)}", invidious_api.comments)
        return [{"author": c["author"], "authoricon": c["authorThumbnails"][-1]["url"], "authorid": c["authorId"], "body": c["contentHtml"].replace("\n", "<br>")} for c in json.loads(text).get("comments", [])]
    except:
        return []

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/api/edu")
async def get_edu_key_route():
    key = await run_in_threadpool(getEduKey)
    return {"key": key} if key else Response(status_code=500)

@app.get('/api/stream_high/{videoid}', response_class=HTMLResponse)
async def embed_high_quality_video(request: Request, videoid: str, proxy: Union[str, None] = Cookie(None)):
    try:
        def fetch():
            res = requests.get(f"https://yudlp-ygug.onrender.com/m3u8/{videoid}", timeout=15, proxies=PROXIES, verify=False).json()
            m3u8 = sorted(res.get('m3u8_formats', []), key=lambda x: int(x.get('resolution','0x0').split('x')[-1]) if 'x' in x.get('resolution','') else 0, reverse=True)
            return {"url": m3u8[0]['url'], "title": res.get('title')}
        d = await run_in_threadpool(fetch)
        return templates.TemplateResponse('embed_high.html', {"request": request, "video_url": d["url"], "audio_url": "", "video_title": d["title"], "videoid": videoid, "proxy": proxy})
    except:
        return Response("Stream Error", status_code=500)

@app.get("/api/stream_360p_url/{videoid}")
async def get_360p_stream_url_route(videoid: str):
    try:
        def fetch():
            res = requests.get(f"{STREAM_YTDL_API_BASE_URL}{videoid}", timeout=max_api_wait_time, proxies=PROXIES, verify=False).json()
            return next(f["url"] for f in res.get("formats", []) if f.get("itag") == "18")
        return {"stream_url": await run_in_threadpool(fetch)}
    except:
        return Response(status_code=500)

@app.get('/api/edu/{videoid}', response_class=HTMLResponse)
async def embed_edu_video(request: Request, videoid: str, proxy: Union[str, None] = Cookie(None)):
    try:
        res = requests.get(f"{EDU_STREAM_API_BASE_URL}{videoid}", timeout=max_api_wait_time, proxies=PROXIES, verify=False).json()
        return templates.TemplateResponse('embed.html', {"request": request, "embed_url": res.get("url"), "videoid": videoid, "proxy": proxy})
    except:
        return Response(status_code=503)

@app.get("/api/short/{channelid}")
async def get_short_data_route(channelid: str):
    try:
        return requests.get(f"{SHORT_STREAM_API_BASE_URL}{urllib.parse.quote(channelid)}", timeout=max_api_wait_time, proxies=PROXIES, verify=False).json()
    except:
        return Response(status_code=503)

@app.get("/api/bbs/posts")
async def get_bbs_posts_route():
    try:
        return requests.get(f"{BBS_EXTERNAL_API_BASE_URL}/posts", timeout=max_api_wait_time, proxies=PROXIES, verify=False).json()
    except:
        return Response(status_code=503)

@app.post("/api/bbs/post")
async def post_new_message_route(request: Request):
    try:
        ip = request.headers.get("x-forwarded-for", "unknown").split(',')[0].strip()
        data = await request.json()
        return requests.post(f"{BBS_EXTERNAL_API_BASE_URL}/post", json=data, headers={"X-Original-Client-IP": ip}, timeout=max_api_wait_time, proxies=PROXIES, verify=False).json()
    except:
        return Response(status_code=500)

@app.get('/', response_class=HTMLResponse)
async def home(request: Request, yuzu_access_granted: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if yuzu_access_granted != "True": return RedirectResponse(url="/gate")
    trending = []
    try: trending = await getTrendingData("jp")
    except: pass
    return templates.TemplateResponse("index.html", {"request": request, "proxy": proxy, "results": trending, "word": ""})

@app.get('/gate', response_class=HTMLResponse)
async def access_gate_get(request: Request):
    return templates.TemplateResponse("access_gate.html", {"request": request, "message": "コードを入力"})

@app.post('/gate')
async def access_gate_post(request: Request, access_code: str = Form(...)):
    if access_code == "yuzu":
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(key="yuzu_access_granted", value="True", max_age=86400, httponly=True)
        return response
    return templates.TemplateResponse("access_gate.html", {"request": request, "message": "無効", "error": True}, status_code=401)

@app.get('/watch', response_class=HTMLResponse)
async def video(v: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    try:
        data = await getVideoData(v)
        return templates.TemplateResponse('video.html', {"request": request, "videoid": v, "videourls": [], "description": data[0]['description_html'], "video_title": data[0]['title'], "author_id": data[0]['author_id'], "author_icon": data[0]['author_thumbnails_url'], "author": data[0]['author'], "length_text": data[0]['length_text'], "view_count": data[0]['view_count'], "like_count": data[0]['like_count'], "subscribers_count": data[0]['subscribers_count'], "recommended_videos": data[1], "proxy": proxy})
    except Exception as e:
        return Response(f"エラー: {str(e)}", status_code=500)

@app.get("/search", response_class=HTMLResponse)
async def search(q: str, request: Request, page: int = 1, proxy: Union[str, None] = Cookie(None)):
    try:
        results = await getSearchData(q, page)
        return templates.TemplateResponse("search.html", {"request": request, "results": results, "word": q, "next": f"/search?q={q}&page={page + 1}", "proxy": proxy})
    except:
        return Response("検索失敗", status_code=500)

@app.get("/channel/{channelid}", response_class=HTMLResponse)
async def channel(channelid: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    data = await getChannelData(channelid)
    return templates.TemplateResponse("channel.html", {"request": request, "results": data[0], "shorts": [], "channel_name": data[1]["channel_name"], "channel_icon": data[1]["channel_icon"], "channel_profile": data[1]["channel_profile"], "cover_img_url": data[1]["author_banner"], "subscribers_count": data[1]["subscribers_count"], "tags": data[1]["tags"], "proxy": proxy})

@app.get("/thumbnail")
async def thumbnail(v: str):
    try:
        res = requests.get(f"https://img.youtube.com/vi/{v}/0.jpg", timeout=3.0, proxies=PROXIES, verify=False)
        return Response(content=res.content, media_type="image/jpeg")
    except:
        return Response(status_code=404) 

@app.get("/suggest")
def suggest(keyword: str):
    try:
        res = requests.get(f"http://www.google.com/complete/search?client=youtube&hl=ja&ds=yt&q={urllib.parse.quote(keyword)}", proxies=PROXIES, verify=False).text
        return [i[0] for i in json.loads(res[19:-1])[1]]
    except:
        return []
