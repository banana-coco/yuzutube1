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
from youtubesearchpython.__future__ import Video

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates")) 

class APITimeoutError(Exception): pass

def getRandomUserAgent(): 
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36'}

def isJSON(json_str):
    try: 
        json.loads(json_str)
        return True
    except json.JSONDecodeError: 
        return False

max_time = 10.0
max_api_wait_time = (3.0, 8.0)
failed = "Load Failed"

EDU_STREAM_API_BASE_URL = "https://siawaseok.duckdns.org/api/stream/" 
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

def requestAPI(path, api_urls):
    apis_to_try = api_urls
    if not apis_to_try:
        raise APITimeoutError("No API instances configured.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(apis_to_try)) as executor:
        future_to_api = {
            executor.submit(
                requests.get, 
                api + 'api/v1' + path, 
                headers=getRandomUserAgent(), 
                timeout=max_api_wait_time
            ): api for api in apis_to_try
        }
        for future in concurrent.futures.as_completed(future_to_api, timeout=max_time):
            try:
                res = future.result()
                if res.status_code == requests.codes.ok and isJSON(res.text):
                    return res.text
            except:
                continue
    raise APITimeoutError("All API instances failed.")

def getEduKey():
    api_url = "https://apis.kahoot.it/media-api/youtube/key"
    try:
        res = requests.get(api_url, headers=getRandomUserAgent(), timeout=max_api_wait_time)
        if isJSON(res.text):
            return json.loads(res.text).get("key")
    except:
        pass
    return None

def formatSearchData(data_dict):
    if data_dict["type"] == "video": 
        return {
            "type": "video", 
            "title": data_dict.get("title", failed), 
            "id": data_dict.get("videoId", failed), 
            "author": data_dict.get("author", failed), 
            "published": data_dict.get("publishedText", failed), 
            "length": str(datetime.timedelta(seconds=data_dict.get("lengthSeconds", 0))), 
            "view_count_text": data_dict.get("viewCountText", failed)
        }
    elif data_dict["type"] == "playlist": 
        return {
            "type": "playlist", 
            "title": data_dict.get("title", failed), 
            "id": data_dict.get('playlistId', failed), 
            "thumbnail": data_dict.get("playlistThumbnail", failed), 
            "count": data_dict.get("videoCount", failed)
        }
    elif data_dict["type"] == "channel":
        thumbnail_url = data_dict.get('authorThumbnails', [{}])[-1].get('url', failed) if data_dict.get('authorThumbnails') else failed
        return {
            "type": "channel", 
            "author": data_dict.get("author", failed), 
            "id": data_dict.get("authorId", failed), 
            "thumbnail": thumbnail_url
        }
    return {"type": "unknown", "data": data_dict}

async def getVideoData(videoid):
    try:
        video_info = await Video.get(videoid)
        if not video_info:
            raise APITimeoutError("Video data not found")

        author_thumbs = video_info.get("channel", {}).get("thumbnails", [])
        author_icon = author_thumbs[-1].get("url", failed) if author_thumbs else failed

        video_details = {
            'video_urls': [], 
            'description_html': video_info.get("description", failed).replace("\n", "<br>"), 
            'title': video_info.get("title", failed),
            'author_id': video_info.get("channel", {}).get("id", failed), 
            'author': video_info.get("channel", {}).get("name", failed), 
            'author_thumbnails_url': author_icon, 
            'view_count': video_info.get("viewCount", {}).get("text", failed), 
            'like_count': "N/A", 
            'subscribers_count': video_info.get("channel", {}).get("subscribers", failed),
            'published_text': video_info.get("publishDate", failed),
            "length_text": video_info.get("duration", {}).get("text", "") 
        }
        
        recommended_videos = []
        for item in video_info.get("suggestions", []):
            thumb_id = item.get("id")
            if "playlistId" in item:
                recommended_videos.append({
                    "type": "playlist",
                    "title": item.get("title", failed), 
                    "id": item.get("id", failed),
                    "author": item.get("channel", {}).get("name", failed),
                    "thumbnail_url": f"https://i.ytimg.com/vi/{thumb_id}/sddefault.jpg"
                })
            else:
                recommended_videos.append({
                    "type": "video", 
                    "id": item.get("id", failed), 
                    "video_id": item.get("id", failed), 
                    "title": item.get("title", failed), 
                    "author_id": item.get("channel", {}).get("id", failed),
                    "author": item.get("channel", {}).get("name", failed), 
                    "length_text": item.get("duration", {}).get("text", failed), 
                    "view_count_text": item.get("viewCount", {}).get("text", failed),
                    "published_text": item.get("publishedTime", failed), 
                    "thumbnail_url": f"https://i.ytimg.com/vi/{thumb_id}/sddefault.jpg"
                })
        return [video_details, recommended_videos]
    except Exception as e:
        raise APITimeoutError(f"Library error: {str(e)}")

async def getSearchData(q, page):
    datas_text = await run_in_threadpool(requestAPI, f"/search?q={urllib.parse.quote(q)}&page={page}&hl=jp", invidious_api.search)
    return [formatSearchData(d) for d in json.loads(datas_text)]

async def getTrendingData(region: str):
    path = f"/trending?region={region}&hl=jp"
    datas_text = await run_in_threadpool(requestAPI, path, invidious_api.search)
    return [formatSearchData(d) for d in json.loads(datas_text) if d.get("type") == "video"]

async def getChannelData(channelid):
    t = {}
    try:
        t_text = await run_in_threadpool(requestAPI, f"/channels/{urllib.parse.quote(channelid)}", invidious_api.channel)
        t = json.loads(t_text)
    except:
        pass
    latest_videos = t.get('latestVideos') or t.get('latestvideo') or []
    author_thumbnails = t.get("authorThumbnails", [])
    author_icon_url = author_thumbnails[-1].get("url", failed) if author_thumbnails else failed
    author_banner_url = urllib.parse.quote(t.get('authorBanners', [{}])[0].get("url", ""), safe="-_.~/:") if t.get('authorBanners') else ""
    return [[
        {
            "type": "video", 
            "title": i.get("title", failed), 
            "id": i.get("videoId", failed), 
            "author": t.get("author", failed), 
            "published": i.get("publishedText", failed), 
            "view_count_text": i.get('viewCountText', failed), 
            "length_str": str(datetime.timedelta(seconds=i.get("lengthSeconds", 0)))
        }
        for i in latest_videos
    ], {
        "channel_name": t.get("author", "取得失敗"), 
        "channel_icon": author_icon_url, 
        "channel_profile": t.get("descriptionHtml", ""),
        "author_banner": author_banner_url,
        "subscribers_count": t.get("subCount", failed), 
        "tags": t.get("tags", [])
    }]

async def getPlaylistData(listid, page):
    t_text = await run_in_threadpool(requestAPI, f"/playlists/{urllib.parse.quote(listid)}?page={urllib.parse.quote(str(page))}", invidious_api.playlist)
    t = json.loads(t_text)["videos"]
    return [{"title": i["title"], "id": i["videoId"], "authorId": i["authorId"], "author": i["author"], "type": "video"} for i in t]

async def getCommentsData(videoid):
    t_text = await run_in_threadpool(requestAPI, f"/comments/{urllib.parse.quote(videoid)}", invidious_api.comments)
    t = json.loads(t_text)["comments"]
    return [{"author": i["author"], "authoricon": i["authorThumbnails"][-1]["url"], "authorid": i["authorId"], "body": i["contentHtml"].replace("\n", "<br>")} for i in t]

def get_ytdl_formats(videoid: str):
    res = requests.get(f"{STREAM_YTDL_API_BASE_URL}{videoid}", headers=getRandomUserAgent(), timeout=max_api_wait_time)
    res.raise_for_status()
    return res.json().get("formats", [])

def get_360p_single_url(videoid: str):
    formats = get_ytdl_formats(videoid)
    target = next((f for f in formats if f.get("itag") == "18" and f.get("url")), None)
    if target: return target["url"]
    raise ValueError("No 360p stream found")

def fetch_high_quality_streams(videoid: str):
    response = requests.get(f"https://yudlp-ygug.onrender.com/m3u8/{videoid}", timeout=15) 
    response.raise_for_status() 
    data = response.json()
    m3u8_formats = sorted([f for f in data.get('m3u8_formats', []) if f.get('url')], key=lambda x: int(x.get('resolution', '0x0').split('x')[-1]), reverse=True)
    if m3u8_formats:
        return {"video_url": m3u8_formats[0]["url"], "audio_url": "", "title": f"[{m3u8_formats[0].get('resolution')}] {data.get('title')}"}
    raise ValueError("No M3U8 found")

async def fetch_embed_url_from_external_api(videoid: str):
    def sync_fetch():
        res = requests.get(f"{EDU_STREAM_API_BASE_URL}{videoid}", headers=getRandomUserAgent(), timeout=max_api_wait_time)
        res.raise_for_status()
        return res.json().get("url")
    return await run_in_threadpool(sync_fetch)

async def fetch_short_data_from_external_api(channelid: str):
    def sync_fetch():
        res = requests.get(f"{SHORT_STREAM_API_BASE_URL}{urllib.parse.quote(channelid)}", headers=getRandomUserAgent(), timeout=max_api_wait_time)
        res.raise_for_status()
        return res.json()
    return await run_in_threadpool(sync_fetch)

async def fetch_bbs_posts():
    def sync_fetch():
        res = requests.get(f"{BBS_EXTERNAL_API_BASE_URL}/posts", headers=getRandomUserAgent(), timeout=max_api_wait_time)
        res.raise_for_status()
        return res.json()
    return await run_in_threadpool(sync_fetch)

async def post_new_message(client_ip: str, name: str, body: str):
    def sync_post():
        res = requests.post(f"{BBS_EXTERNAL_API_BASE_URL}/post", json={"name": name, "body": body}, headers={**getRandomUserAgent(), "X-Original-Client-IP": client_ip}, timeout=max_api_wait_time)
        res.raise_for_status()
        return res.json()
    return await run_in_threadpool(sync_post)

app = FastAPI()
invidious_api = InvidiousAPI() 

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/api/edu")
async def get_edu_key_route():
    key = await run_in_threadpool(getEduKey)
    return {"key": key} if key else Response(content='{"error": "failed"}', media_type="application/json", status_code=500)

@app.get('/api/stream_high/{videoid}', response_class=HTMLResponse)
async def embed_high_quality_video(request: Request, videoid: str, proxy: Union[str, None] = Cookie(None)):
    try:
        stream_data = await run_in_threadpool(fetch_high_quality_streams, videoid)
        return templates.TemplateResponse('embed_high.html', {"request": request, "video_url": stream_data["video_url"], "audio_url": stream_data["audio_url"], "video_title": stream_data["title"], "videoid": videoid, "proxy": proxy})
    except Exception as e:
        return Response(str(e), status_code=500)

@app.get("/api/stream_360p_url/{videoid}")
async def get_360p_stream_url_route(videoid: str):
    try:
        url = await run_in_threadpool(get_360p_single_url, videoid)
        return {"stream_url": url}
    except Exception as e:
        return Response(content=f'{{"error": "{str(e)}"}}', media_type="application/json", status_code=500)

@app.get('/api/edu/{videoid}', response_class=HTMLResponse)
async def embed_edu_video(request: Request, videoid: str, proxy: Union[str, None] = Cookie(None)):
    try:
        embed_url = await fetch_embed_url_from_external_api(videoid)
        return templates.TemplateResponse('embed.html', {"request": request, "embed_url": embed_url, "videoid": videoid, "proxy": proxy})
    except Exception as e:
        return Response(str(e), status_code=503)

@app.get("/api/short/{channelid}")
async def get_short_data_route(channelid: str):
    try:
        return await fetch_short_data_from_external_api(channelid)
    except Exception as e:
        return Response(content=f'{{"error": "{str(e)}"}}', media_type="application/json", status_code=503)

@app.get("/api/bbs/posts")
async def get_bbs_posts_route():
    try:
        return await fetch_bbs_posts()
    except Exception as e:
        return Response(content=str(e), media_type="application/json", status_code=500)

@app.post("/api/bbs/post")
async def post_new_message_route(request: Request):
    try:
        client_ip = request.headers.get("x-forwarded-for", "unknown").split(',')[0].strip()
        data = await request.json()
        return await post_new_message(client_ip, data.get("name", ""), data.get("body", ""))
    except Exception as e:
        return Response(content=str(e), media_type="application/json", status_code=500)

@app.get('/', response_class=HTMLResponse)
async def home(request: Request, yuzu_access_granted: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if yuzu_access_granted != "True": return RedirectResponse(url="/gate", status_code=302)
    trending = []
    try: trending = await getTrendingData("jp")
    except: pass
    return templates.TemplateResponse("index.html", {"request": request, "proxy": proxy, "results": trending, "word": ""})

@app.get('/gate', response_class=HTMLResponse)
async def access_gate_get(request: Request):
    return templates.TemplateResponse("access_gate.html", {"request": request, "message": "コードを入力してください。"})

@app.post('/gate')
async def access_gate_post(request: Request, access_code: str = Form(...)):
    if access_code == "yuzu":
        response = RedirectResponse(url="/", status_code=302)
        expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        response.set_cookie(key="yuzu_access_granted", value="True", expires=expires.strftime("%a, %d-%b-%Y %H:%M:%S GMT"), httponly=True)
        return response
    return templates.TemplateResponse("access_gate.html", {"request": request, "message": "無効なコードです。", "error": True}, status_code=401)

@app.get('/bbs', response_class=HTMLResponse)
async def bbs(request: Request):
    return templates.TemplateResponse("bbs.html", {"request": request})

@app.get('/watch', response_class=HTMLResponse)
async def video(v: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    data = await getVideoData(v)
    return templates.TemplateResponse('video.html', {
        "request": request, "videoid": v, "videourls": data[0]['video_urls'], "high_quality_url": "",
        "description": data[0]['description_html'], "video_title": data[0]['title'], 
        "author_id": data[0]['author_id'], "author_icon": data[0]['author_thumbnails_url'], 
        "author": data[0]['author'], "length_text": data[0]['length_text'], 
        "view_count": data[0]['view_count'], "like_count": data[0]['like_count'], 
        "subscribers_count": data[0]['subscribers_count'], "recommended_videos": data[1], "proxy": proxy
    })

@app.get("/search", response_class=HTMLResponse)
async def search(q: str, request: Request, page: Union[int, None] = 1, proxy: Union[str, None] = Cookie(None)):
    results = await getSearchData(q, page)
    return templates.TemplateResponse("search.html", {"request": request, "results": results, "word": q, "next": f"/search?q={q}&page={page + 1}", "proxy": proxy})

@app.get("/hashtag/{tag}")
async def hashtag_search(tag: str):
    return RedirectResponse(f"/search?q={urllib.parse.quote(tag)}", status_code=302)

@app.get("/channel/{channelid}", response_class=HTMLResponse)
async def channel(channelid: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    data = await getChannelData(channelid)
    shorts = []
    try:
        shorts_data = await fetch_short_data_from_external_api(channelid)
        shorts = shorts_data if isinstance(shorts_data, list) else shorts_data.get("videos", [])
    except: pass
    return templates.TemplateResponse("channel.html", {
        "request": request, "results": data[0], "shorts": shorts,  
        "channel_name": data[1]["channel_name"], "channel_icon": data[1]["channel_icon"], 
        "channel_profile": data[1]["channel_profile"], "cover_img_url": data[1]["author_banner"], 
        "subscribers_count": data[1]["subscribers_count"], "tags": data[1]["tags"], "proxy": proxy
    })

@app.get("/playlist", response_class=HTMLResponse)
async def playlist(list: str, request: Request, page: Union[int, None] = 1, proxy: Union[str, None] = Cookie(None)):
    data = await getPlaylistData(list, str(page))
    return templates.TemplateResponse("search.html", {"request": request, "results": data, "word": "", "next": f"/playlist?list={list}&page={page + 1}", "proxy": proxy})

@app.get("/comments", response_class=HTMLResponse)
async def comments(request: Request, v: str):
    data = await getCommentsData(v)
    return templates.TemplateResponse("comments.html", {"request": request, "comments": data})

@app.get("/thumbnail")
async def thumbnail(v: str):
    try:
        res = requests.get(f"https://img.youtube.com/vi/{v}/0.jpg", timeout=3.0)
        return Response(content=res.content, media_type="image/jpeg")
    except:
        return Response(status_code=404) 

@app.get("/suggest")
def suggest(keyword: str):
    res = requests.get(f"http://www.google.com/complete/search?client=youtube&hl=ja&ds=yt&q={urllib.parse.quote(keyword)}", headers=getRandomUserAgent()).text
    return [i[0] for i in json.loads(res[19:-1])[1]]
