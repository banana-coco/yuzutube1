import json
import time
import requests
import datetime
import urllib.parse
from pathlib import Path 
from typing import Union, List, Dict, Any
import asyncio 
from fastapi import FastAPI, Response, Request, Cookie, Form 
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool 

# YouTube Search Python のインポート
from youtubesearchpython import VideosSearch, ChannelsSearch, PlaylistsSearch, Video, Channel, Playlist, Comments, Suggestions

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates")) 

class APITimeoutError(Exception): pass

def getRandomUserAgent(): 
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36'}

max_api_wait_time = (3.0, 8.0)
failed = "Load Failed"

EDU_STREAM_API_BASE_URL = "https://siawaseok.duckdns.org/api/stream/" 
EDU_VIDEO_API_BASE_URL = "https://siawaseok.duckdns.org/api/video2/"
STREAM_YTDL_API_BASE_URL = "https://yudlp-ygug.onrender.com/stream/" 
SHORT_STREAM_API_BASE_URL = "https://yt-dl-kappa.vercel.app/short/"
BBS_EXTERNAL_API_BASE_URL = "https://server-bbs.vercel.app"

def getEduKey():
    api_url = "https://apis.kahoot.it/media-api/youtube/key"
    try:
        res = requests.get(api_url, headers=getRandomUserAgent(), timeout=max_api_wait_time)
        res.raise_for_status() 
        
        if res.text and res.text.strip():
            data = json.loads(res.text)
            return data.get("key")
        
    except requests.exceptions.RequestException:
        pass
    except json.JSONDecodeError:
        pass
    
    return None

def format_duration(seconds):
    """秒数をHH:MM:SS形式に変換"""
    if not seconds or seconds == 0:
        return "0:00"
    return str(datetime.timedelta(seconds=seconds))

def format_view_count(views):
    """再生回数を日本語形式に変換"""
    if not views:
        return "不明"
    try:
        views_int = int(views)
        if views_int >= 100000000:
            return f"{views_int / 100000000:.1f}億回視聴"
        elif views_int >= 10000:
            return f"{views_int / 10000:.1f}万回視聴"
        else:
            return f"{views_int:,}回視聴"
    except:
        return str(views)

def format_subscriber_count(subs):
    """チャンネル登録者数を日本語形式に変換"""
    if not subs:
        return "不明"
    try:
        subs_str = str(subs).replace(',', '').replace('人', '').strip()
        subs_int = int(subs_str)
        if subs_int >= 100000000:
            return f"{subs_int / 100000000:.1f}億人"
        elif subs_int >= 10000:
            return f"{subs_int / 10000:.1f}万人"
        else:
            return f"{subs_int:,}人"
    except:
        return str(subs)

async def getVideoData(videoid):
    """動画情報を取得"""
    def sync_fetch():
        try:
            video_info = Video.getInfo(videoid)
            
            if not video_info:
                raise APITimeoutError("動画情報の取得に失敗しました")
            
            # 説明文の取得
            description = video_info.get('description', failed)
            if isinstance(description, dict):
                description = description.get('text', failed)
            
            # チャンネル情報の取得
            channel_info = video_info.get('channel', {})
            channel_id = channel_info.get('id', failed)
            channel_name = channel_info.get('name', failed)
            
            # サムネイルの取得
            thumbnails = channel_info.get('thumbnails', [])
            channel_thumbnail = thumbnails[-1].get('url', failed) if thumbnails else failed
            
            # 視聴回数とライク数
            view_count = video_info.get('viewCount', {}).get('text', failed)
            likes = video_info.get('likes', failed)
            
            # 公開日
            published_date = video_info.get('publishDate', failed)
            
            # 動画の長さ
            duration_seconds = video_info.get('duration', {}).get('secondsText', 0)
            try:
                duration_seconds = int(duration_seconds)
            except:
                duration_seconds = 0
            
            # 関連動画の取得
            related_videos = []
            try:
                suggestions = video_info.get('suggestions', [])
                for item in suggestions[:20]:  # 最大20件
                    if item.get('type') == 'video':
                        related_videos.append({
                            "type": "video",
                            "id": item.get('id', failed),
                            "video_id": item.get('id', failed),
                            "title": item.get('title', failed),
                            "author": item.get('channel', {}).get('name', failed),
                            "author_id": item.get('channel', {}).get('id', failed),
                            "length_text": format_duration(item.get('duration', {}).get('secondsText', 0)),
                            "view_count_text": item.get('viewCount', {}).get('text', failed),
                            "published_text": item.get('publishedTime', failed),
                            "thumbnail_url": f"https://i.ytimg.com/vi/{item.get('id', '')}/sddefault.jpg"
                        })
            except Exception as e:
                print(f"関連動画取得エラー: {e}")
            
            video_details = {
                'video_urls': [],
                'description_html': description.replace('\n', '<br>') if description != failed else failed,
                'title': video_info.get('title', failed),
                'author_id': channel_id,
                'author': channel_name,
                'author_thumbnails_url': channel_thumbnail,
                'view_count': view_count,
                'like_count': str(likes) if likes != failed else failed,
                'subscribers_count': channel_info.get('subscribers', {}).get('simpleText', failed),
                'published_text': published_date,
                'length_text': format_duration(duration_seconds)
            }
            
            return [video_details, related_videos]
            
        except Exception as e:
            raise APITimeoutError(f"動画情報の取得エラー: {str(e)}")
    
    return await run_in_threadpool(sync_fetch)

async def getSearchData(q, page):
    """検索結果を取得"""
    def sync_search():
        try:
            limit = 20
            offset = (page - 1) * limit
            
            # 動画検索
            videos_search = VideosSearch(q, limit=limit, offset=offset)
            videos_result = videos_search.result()
            
            results = []
            
            if videos_result and 'result' in videos_result:
                for video in videos_result['result']:
                    duration_text = video.get('duration', '0:00')
                    view_count = video.get('viewCount', {})
                    
                    results.append({
                        "type": "video",
                        "title": video.get('title', failed),
                        "id": video.get('id', failed),
                        "author": video.get('channel', {}).get('name', failed),
                        "published": video.get('publishedTime', failed),
                        "length": duration_text,
                        "view_count_text": view_count.get('short', failed) if isinstance(view_count, dict) else str(view_count)
                    })
            
            # ページ1の場合のみチャンネル検索も追加
            if page == 1:
                try:
                    channels_search = ChannelsSearch(q, limit=3)
                    channels_result = channels_search.result()
                    
                    if channels_result and 'result' in channels_result:
                        for channel in channels_result['result']:
                            thumbnails = channel.get('thumbnails', [])
                            thumbnail_url = thumbnails[-1].get('url', failed) if thumbnails else failed
                            
                            results.append({
                                "type": "channel",
                                "author": channel.get('title', failed),
                                "id": channel.get('id', failed),
                                "thumbnail": thumbnail_url
                            })
                except:
                    pass
            
            return results
            
        except Exception as e:
            raise APITimeoutError(f"検索エラー: {str(e)}")
    
    return await run_in_threadpool(sync_search)

async def getTrendingData(region: str):
    """トレンド動画を取得（検索で代用）"""
    try:
        # トレンドの代わりに人気の動画を検索
        videos_search = VideosSearch("", limit=20, region=region)
        videos_result = videos_search.result()
        
        results = []
        if videos_result and 'result' in videos_result:
            for video in videos_result['result']:
                duration_text = video.get('duration', '0:00')
                view_count = video.get('viewCount', {})
                
                results.append({
                    "type": "video",
                    "title": video.get('title', failed),
                    "id": video.get('id', failed),
                    "author": video.get('channel', {}).get('name', failed),
                    "published": video.get('publishedTime', failed),
                    "length": duration_text,
                    "view_count_text": view_count.get('short', failed) if isinstance(view_count, dict) else str(view_count)
                })
        
        return results
    except:
        return []

async def getChannelData(channelid):
    """チャンネル情報を取得"""
    def sync_fetch():
        try:
            channel_info = Channel.get(channelid)
            
            if not channel_info:
                raise APITimeoutError("チャンネル情報の取得に失敗しました")
            
            # 最新動画の取得
            latest_videos = []
            videos = channel_info.get('uploads', {}).get('videos', [])
            
            for video in videos[:30]:  # 最大30件
                duration_seconds = video.get('duration', {}).get('secondsText', 0)
                try:
                    duration_seconds = int(duration_seconds)
                except:
                    duration_seconds = 0
                
                view_count = video.get('viewCount', {})
                
                latest_videos.append({
                    "type": "video",
                    "title": video.get('title', failed),
                    "id": video.get('id', failed),
                    "author": channel_info.get('title', failed),
                    "published": video.get('publishedTime', failed),
                    "view_count_text": view_count.get('text', failed) if isinstance(view_count, dict) else str(view_count),
                    "length_str": format_duration(duration_seconds)
                })
            
            # チャンネルアイコン
            thumbnails = channel_info.get('thumbnails', [])
            channel_icon = thumbnails[-1].get('url', failed) if thumbnails else failed
            
            # チャンネルバナー
            banners = channel_info.get('banners', [])
            channel_banner = banners[-1].get('url', '') if banners else ''
            
            # 説明文
            description = channel_info.get('description', 'このチャンネルのプロフィール情報は見つかりませんでした。')
            if isinstance(description, dict):
                description = description.get('text', 'このチャンネルのプロフィール情報は見つかりませんでした。')
            
            # チャンネル登録者数
            subscribers = channel_info.get('subscribers', {})
            if isinstance(subscribers, dict):
                subscribers_text = subscribers.get('simpleText', failed)
            else:
                subscribers_text = format_subscriber_count(subscribers)
            
            channel_data = {
                "channel_name": channel_info.get('title', "チャンネル情報取得失敗"),
                "channel_icon": channel_icon,
                "channel_profile": description.replace('\n', '<br>'),
                "author_banner": channel_banner,
                "subscribers_count": subscribers_text,
                "tags": channel_info.get('tags', [])
            }
            
            return [latest_videos, channel_data]
            
        except Exception as e:
            raise APITimeoutError(f"チャンネル情報の取得エラー: {str(e)}")
    
    return await run_in_threadpool(sync_fetch)

async def getPlaylistData(listid, page):
    """プレイリスト情報を取得"""
    def sync_fetch():
        try:
            playlist_info = Playlist.get(listid)
            
            if not playlist_info:
                raise APITimeoutError("プレイリスト情報の取得に失敗しました")
            
            videos = playlist_info.get('videos', [])
            
            # ページネーション
            limit = 20
            start = (page - 1) * limit
            end = start + limit
            
            results = []
            for video in videos[start:end]:
                results.append({
                    "title": video.get('title', failed),
                    "id": video.get('id', failed),
                    "authorId": video.get('channel', {}).get('id', failed),
                    "author": video.get('channel', {}).get('name', failed),
                    "type": "video"
                })
            
            return results
            
        except Exception as e:
            raise APITimeoutError(f"プレイリスト情報の取得エラー: {str(e)}")
    
    return await run_in_threadpool(sync_fetch)

async def getCommentsData(videoid):
    """コメントを取得"""
    def sync_fetch():
        try:
            comments_obj = Comments(videoid)
            comments_data = comments_obj.comments
            
            if not comments_data or 'result' not in comments_data:
                return []
            
            results = []
            for comment in comments_data['result'][:50]:  # 最大50件
                author_thumbnails = comment.get('author', {}).get('thumbnails', [])
                author_icon = author_thumbnails[-1].get('url', failed) if author_thumbnails else failed
                
                # コメント本文
                content = comment.get('content', '')
                if isinstance(content, dict):
                    content = content.get('text', '')
                
                results.append({
                    "author": comment.get('author', {}).get('name', failed),
                    "authoricon": author_icon,
                    "authorid": comment.get('author', {}).get('id', failed),
                    "body": content.replace('\n', '<br>')
                })
            
            return results
            
        except Exception as e:
            print(f"コメント取得エラー: {str(e)}")
            return []
    
    return await run_in_threadpool(sync_fetch)

def fetch_video_data_from_edu_api(videoid: str):
    target_url = f"{EDU_VIDEO_API_BASE_URL}{urllib.parse.quote(videoid)}"
    
    res = requests.get(
        target_url, 
        headers=getRandomUserAgent(), 
        timeout=max_api_wait_time
    )
    res.raise_for_status()
    return res.json()

def get_ytdl_formats(videoid: str) -> List[Dict[str, Any]]:
    target_url = f"{STREAM_YTDL_API_BASE_URL}{videoid}"
    
    res = requests.get(
        target_url, 
        headers=getRandomUserAgent(), 
        timeout=max_api_wait_time
    )
    res.raise_for_status()
    data = res.json()
    
    formats: List[Dict[str, Any]] = data.get("formats", [])
    if not formats:
        raise ValueError("Stream API response is missing video formats.")
        
    return formats

def get_360p_single_url(videoid: str) -> str:
    try:
        formats = get_ytdl_formats(videoid)
        
        target_format = next((
            f for f in formats 
            if f.get("itag") == "18" and f.get("url") 
        ), None)
        
        if target_format and target_format.get("url"):
            return target_format["url"]
            
        raise ValueError("Could not find a combined 360p stream (itag 18) in the API response.")

    except requests.exceptions.HTTPError as e:
        raise APITimeoutError(f"Stream API returned HTTP error: {e.response.status_code}") from e
    except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError) as e:
        raise APITimeoutError(f"Error processing stream API response for 360p: {e}") from e

def fetch_high_quality_streams(videoid: str) -> Dict[str, str]:
    API_URL = f"https://yudlp-ygug.onrender.com/m3u8/{videoid}"

    try:
        response = requests.get(API_URL, timeout=15) 
        response.raise_for_status() 
        data = response.json()
        
        m3u8_formats = data.get('m3u8_formats', [])
        
        if not m3u8_formats:
            raise ValueError("No M3U8 formats found in the API response.")

        def get_height(f):
            resolution_str = f.get('resolution', '0x0')
            try:
                return int(resolution_str.split('x')[-1]) if 'x' in resolution_str else 0
            except ValueError:
                return 0

        m3u8_formats_sorted = sorted(
            [f for f in m3u8_formats if f.get('url')],
            key=get_height,
            reverse=True
        )
        
        if m3u8_formats_sorted:
            best_m3u8 = m3u8_formats_sorted[0]
            
            title = data.get("title", f"Stream for {videoid}")
            resolution = best_m3u8.get('resolution', 'Highest Quality')
            
            return {
                "video_url": best_m3u8["url"],
                "audio_url": "",
                "title": f"[{resolution}] Stream for {title}"
            }

        raise ValueError("Could not find any suitable high-quality stream (M3U8) in the API response after sorting.")

    except requests.exceptions.HTTPError as e:
        raise APITimeoutError(f"Stream API returned HTTP error: {e.response.status_code} for {API_URL}") from e
    except requests.exceptions.Timeout as e:
        raise APITimeoutError(f"Stream API request timed out for {API_URL}") from e
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        raise APITimeoutError(f"Error processing stream API response: {e}") from e
    except ValueError as e:
        raise e

async def fetch_embed_url_from_external_api(videoid: str) -> str:
    target_url = f"{EDU_STREAM_API_BASE_URL}{videoid}"
    
    def sync_fetch():
        res = requests.get(
            target_url, 
            headers=getRandomUserAgent(), 
            timeout=max_api_wait_time
        )
        res.raise_for_status()
        data = res.json()
        
        embed_url = data.get("url")
        if not embed_url:
            raise ValueError("External API response is missing the 'url' field.")
            
        return embed_url

    return await run_in_threadpool(sync_fetch)

async def fetch_short_data_from_external_api(channelid: str) -> Dict[str, Any]:
    target_url = f"{SHORT_STREAM_API_BASE_URL}{urllib.parse.quote(channelid)}"
    
    def sync_fetch():
        res = requests.get(
            target_url, 
            headers=getRandomUserAgent(), 
            timeout=max_api_wait_time 
        )
        res.raise_for_status()
        return res.json()

    return await run_in_threadpool(sync_fetch)

async def fetch_bbs_posts():
    target_url = f"{BBS_EXTERNAL_API_BASE_URL}/posts"
    
    def sync_fetch():
        res = requests.get(
            target_url, 
            headers=getRandomUserAgent(), 
            timeout=max_api_wait_time
        )
        res.raise_for_status()
        return res.json()

    return await run_in_threadpool(sync_fetch)

async def post_new_message(client_ip: str, name: str, body: str):
    target_url = f"{BBS_EXTERNAL_API_BASE_URL}/post"
    
    def sync_post():
        headers = {
            **getRandomUserAgent(), 
            "X-Original-Client-IP": client_ip
        }
        
        res = requests.post(
            target_url, 
            json={"name": name, "body": body},
            headers=headers,
            timeout=max_api_wait_time
        )
        res.raise_for_status()
        return res.json()

    return await run_in_threadpool(sync_post)

app = FastAPI()

app.mount(
    "/static", 
    StaticFiles(directory=str(BASE_DIR / "static")), 
    name="static"
)

@app.get("/api/edu")
async def get_edu_key_route():
    key = await run_in_threadpool(getEduKey)
    
    if key:
        return {"key": key}
    else:
        return Response(content='{"error": "Failed to retrieve key from Kahoot API"}', media_type="application/json", status_code=500)

@app.get('/api/stream_high/{videoid}', response_class=HTMLResponse)
async def embed_high_quality_video(request: Request, videoid: str, proxy: Union[str, None] = Cookie(None)):
    try:
        stream_data = await run_in_threadpool(fetch_high_quality_streams, videoid)
        
    except APITimeoutError as e:
        return Response(f"Failed to retrieve high-quality stream URL: {e}", status_code=503)
        
    except Exception as e:
        return Response("An unexpected error occurred while retrieving stream data.", status_code=500)

    return templates.TemplateResponse(
        'embed_high.html', 
        {
            "request": request, 
            "video_url": stream_data["video_url"],
            "audio_url": stream_data["audio_url"],
            "video_title": stream_data["title"],
            "videoid": videoid,
            "proxy": proxy
        }
    )

@app.get("/api/stream_360p_url/{videoid}")
async def get_360p_stream_url_route(videoid: str):
    try:
        url = await run_in_threadpool(get_360p_single_url, videoid)
        return {"stream_url": url}
    except APITimeoutError as e:
        return Response(content=f'{{"error": "Failed to get stream URL after multiple attempts: {str(e)}"}}', media_type="application/json", status_code=503)
    except Exception as e:
        return Response(content=f'{{"error": "An unexpected error occurred: {str(e)}"}}', media_type="application/json", status_code=500)

@app.get('/api/edu/{videoid}', response_class=HTMLResponse)
async def embed_edu_video(request: Request, videoid: str, proxy: Union[str, None] = Cookie(None)):
    embed_url = None
    try:
        embed_url = await fetch_embed_url_from_external_api(videoid)
        
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        if status_code == 404:
            return Response(f"Stream URL for videoid '{videoid}' not found.", status_code=404)
        
        return Response("Failed to retrieve stream URL from external service (HTTP Error).", status_code=503)
        
    except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError):
        return Response("Failed to retrieve stream URL from external service (Connection/Format Error).", status_code=503)

    return templates.TemplateResponse(
        'embed.html', 
        {
            "request": request, 
            "embed_url": embed_url,
            "videoid": videoid,
            "proxy": proxy
        }
    )

@app.get("/api/short/{channelid}")
async def get_short_data_route(channelid: str):
    try:
        data = await fetch_short_data_from_external_api(channelid)
        return data
        
    except Exception as e:
        return Response(
            content=f'{{"error": "Failed to retrieve Shorts data from external service: {str(e)}"}}', 
            media_type="application/json", 
            status_code=503
        )

@app.get("/api/bbs/posts")
async def get_bbs_posts_route():
    try:
        posts_data = await fetch_bbs_posts()
        return posts_data
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        return Response(content=e.response.text, media_type="application/json", status_code=status_code)
    except requests.exceptions.RequestException as e:
        return Response(content=f'{{"detail": "BBS API connection error or timeout: {str(e)}"}}', media_type="application/json", status_code=503)
    except Exception as e:
        return Response(content=f'{{"detail": "An unexpected error occurred: {str(e)}"}}', media_type="application/json", status_code=500)

@app.post("/api/bbs/post")
async def post_new_message_route(request: Request):
    try:
        client_ip = request.headers.get("x-forwarded-for", "unknown").split(',')[0].strip()
        
        data = await request.json()
        name = data.get("name", "")
        body = data.get("body", "")
        
        if not body:
            return Response(content='{"detail": "Body is required"}', media_type="application/json", status_code=400)

        post_response = await post_new_message(client_ip, name, body)
        return post_response
        
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        return Response(content=e.response.text, media_type="application/json", status_code=status_code)
    except requests.exceptions.RequestException as e:
        return Response(content=f'{{"detail": "BBS API connection error or timeout: {str(e)}"}}', media_type="application/json", status_code=503)
    except Exception as e:
        return Response(content=f'{{"detail": "An unexpected error occurred: {str(e)}"}}', media_type="application/json", status_code=500)

@app.get('/', response_class=HTMLResponse)
async def home(request: Request, yuzu_access_granted: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if yuzu_access_granted != "True":
        return RedirectResponse(url="/gate", status_code=302)
    
    trending_videos = []
    try:
        trending_videos = await getTrendingData("jp")
    except Exception:
        pass
        
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "proxy": proxy,
        "results": trending_videos,
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
    CORRECT_CODE = "yuzu"
    
    if access_code == CORRECT_CODE:
        response = RedirectResponse(url="/", status_code=302)
        
        expires_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        response.set_cookie(
            key="yuzu_access_granted", 
            value="True", 
            expires=expires_time.strftime("%a, %d-%b-%Y %H:%M:%S GMT"), 
            httponly=True
        )
        return response
    else:
        return templates.TemplateResponse("access_gate.html", {
            "request": request,
            "message": "無効なアクセスコードです。もう一度入力してください。",
            "error": True
        }, status_code=401)
        
@app.get('/bbs', response_class=HTMLResponse)
async def bbs(request: Request):
    return templates.TemplateResponse("bbs.html", {"request": request})

@app.get('/watch', response_class=HTMLResponse)
async def video(v: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    video_data = await getVideoData(v)
    
    high_quality_url = ""
    
    return templates.TemplateResponse('video.html', {
        "request": request, 
        "videoid": v, 
        "videourls": video_data[0]['video_urls'], 
        "high_quality_url": high_quality_url,
        "description": video_data[0]['description_html'], 
        "video_title": video_data[0]['title'], 
        "author_id": video_data[0]['author_id'], 
        "author_icon": video_data[0]['author_thumbnails_url'], 
        "author": video_data[0]['author'], 
        "length_text": video_data[0]['length_text'], 
        "view_count": video_data[0]['view_count'], 
        "like_count": video_data[0]['like_count'], 
        "subscribers_count": video_data[0]['subscribers_count'], 
        "recommended_videos": video_data[1], 
        "proxy": proxy
    })

@app.get("/search", response_class=HTMLResponse)
async def search(q: str, request: Request, page: Union[int, None] = 1, proxy: Union[str, None] = Cookie(None)):
    search_results = await getSearchData(q, page)
    return templates.TemplateResponse("search.html", {
        "request": request, 
        "results": search_results, 
        "word": q, 
        "next": f"/search?q={q}&page={page + 1}", 
        "proxy": proxy
    })

@app.get("/hashtag/{tag}")
async def hashtag_search(tag: str):
    return RedirectResponse(f"/search?q={urllib.parse.quote(tag)}", status_code=302)

@app.get("/channel/{channelid}", response_class=HTMLResponse)
async def channel(channelid: str, request: Request, proxy: Union[str, None] = Cookie(None)):
    channel_data = await getChannelData(channelid)
    latest_videos = channel_data[0]
    channel_info = channel_data[1]
    
    shorts_videos = []
    try:
        shorts_data = await fetch_short_data_from_external_api(channelid)
        
        if isinstance(shorts_data, list):
            shorts_videos = shorts_data
        elif isinstance(shorts_data, dict) and "videos" in shorts_data:
            shorts_videos = shorts_data["videos"]
        
    except Exception:
        shorts_videos = [] 
        
    return templates.TemplateResponse("channel.html", {
        "request": request, 
        "results": latest_videos, 
        "shorts": shorts_videos,  
        "channel_name": channel_info["channel_name"], 
        "channel_icon": channel_info["channel_icon"], 
        "channel_profile": channel_info["channel_profile"], 
        "cover_img_url": channel_info["author_banner"], 
        "subscribers_count": channel_info["subscribers_count"], 
        "tags": channel_info["tags"], 
        "proxy": proxy
    })

@app.get("/playlist", response_class=HTMLResponse)
async def playlist(list: str, request: Request, page: Union[int, None] = 1, proxy: Union[str, None] = Cookie(None)):
    playlist_data = await getPlaylistData(list, page)
    return templates.TemplateResponse("search.html", {
        "request": request, 
        "results": playlist_data, 
        "word": "", 
        "next": f"/playlist?list={list}&page={page + 1}", 
        "proxy": proxy
    })

@app.get("/comments", response_class=HTMLResponse)
async def comments(request: Request, v: str):
    comments_data = await getCommentsData(v)
    return templates.TemplateResponse("comments.html", {
        "request": request, 
        "comments": comments_data
    })

@app.get("/thumbnail")
async def thumbnail(v: str):
    def sync_fetch_thumbnail(video_id: str):
        res = requests.get(f"https://img.youtube.com/vi/{video_id}/0.jpg", timeout=(1.0, 3.0)) 
        res.raise_for_status()
        return res.content

    try:
        content = await run_in_threadpool(sync_fetch_thumbnail, v)
        return Response(content=content, media_type="image/jpeg")
    except requests.exceptions.RequestException:
        return Response(status_code=404) 

@app.get("/suggest")
async def suggest(keyword: str):
    """検索サジェストを取得"""
    def sync_suggestions():
        try:
            suggestions_obj = Suggestions(language='ja', region='JP')
            suggestions = suggestions_obj.get(keyword)
            
            if suggestions and 'result' in suggestions:
                return [item for item in suggestions['result']]
            return []
        except:
            return []
    
    result = await run_in_threadpool(sync_suggestions)
    return result
