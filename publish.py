# -*- coding: utf-8 -*-
"""
BAW 212 България — автоматично публикуване във Facebook и Instagram.

Пуска се от GitHub Actions на всеки 15 минути. Всеки път:
  1. чете posts.json (постовете с дата и час по София),
  2. публикува тези, чийто час е настъпил и още не са публикувани,
  3. записва резултата в state.json, за да не публикува нищо два пъти.

Всеки пост има едно от трите:
  "image"   един кадър
  "images"  списък кадри — излиза карусел, най-много 10, в двете мрежи
  "video"   видео файл — във Facebook като видео, в Instagram като Reel

Ръчни режими:
  python publish.py --check     проверява токена, профилите и дали всички снимки се отварят
  python publish.py --dry-run   показва какво би публикувал сега, без да публикува
  python publish.py --test      пробна публикация: скрита във Facebook, неизпратена в Instagram
  python publish.py --list      целият график със статус

Нужни променливи (GitHub → Settings → Secrets and variables → Actions):
  META_PAGE_TOKEN   токен за достъп на страницата (таен)
  FB_PAGE_ID        ID на Facebook страницата
  IG_USER_ID        ID на Instagram Business профила
  IMAGE_BASE_URL    публичният адрес на снимките, напр. https://ime.github.io/baw212-autopost
  GRAPH_VERSION     по желание, по подразбиране v25.0
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.json")
STATE = os.path.join(HERE, "state.json")
SOFIA = ZoneInfo("Europe/Sofia")
LATE_LIMIT = timedelta(hours=12)   # ако нещо е закъсняло повече, не го пускаме сляпо

GRAPH = "https://graph.facebook.com/" + os.environ.get("GRAPH_VERSION", "v25.0")


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        sys.exit(f"Липсва променливата {name}. Добави я в GitHub → Settings → Secrets and variables → Actions.")
    return v


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def when_utc(post):
    local = datetime.fromisoformat(post["when"]).replace(tzinfo=SOFIA)
    return local.astimezone(timezone.utc)


def api(method, path, params):
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode(), method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            msg = body
        raise RuntimeError(f"Meta отказа ({e.code}): {msg}") from None


def image_url(name):
    return env("IMAGE_BASE_URL").rstrip("/") + "/" + urllib.parse.quote(name)


def images(post):
    """Един кадър или няколко (карусел). Мрежите приемат най-много 10."""
    lst = post.get("images") or [post["image"]]
    return lst[:10]


def add_comment(target_id, text, token):
    """Първи коментар под публикацията — там слагаме линка, защото Facebook
       намалява обхвата на постове с външен линк в самия текст."""
    if not text:
        return
    try:
        api("POST", f"{target_id}/comments", {"message": text, "access_token": token})
        print("   + първи коментар")
    except Exception as e:
        print("   ! коментарът не мина:", e)


def publish_facebook(post, token, page_id):
    if post.get("video"):
        r = api("POST", f"{page_id}/videos", {
            "file_url": image_url(post["video"]),
            "description": post["caption"],
            "access_token": token,
        })
        pid = r.get("id")
        print("   видео")
        add_comment(pid, post.get("comment"), token)
        return pid
    imgs = images(post)
    if len(imgs) == 1:
        params = {"url": image_url(imgs[0]), "message": post["caption"], "access_token": token}
        if post.get("alt"):
            params["alt_text_custom"] = post["alt"]
        r = api("POST", f"{page_id}/photos", params)
        pid = r.get("post_id") or r.get("id")
    else:
        # карусел: първо качваме кадрите скрити, после ги закачаме към една публикация
        alts = post.get("alts") or []          # буквално — за екранни четци и за Meta
        caps = post.get("captions") or []      # за хората — вижда се при отваряне на кадъра
        fbids = []
        for i, name in enumerate(imgs):
            up = {"url": image_url(name), "published": "false", "access_token": token}
            a = alts[i] if i < len(alts) else post.get("alt")
            if a:
                up["alt_text_custom"] = a
            c = caps[i] if i < len(caps) else None
            if c:
                up["caption"] = c
            fbids.append(api("POST", f"{page_id}/photos", up)["id"])
        params = {"message": post["caption"], "access_token": token}
        for i, fid in enumerate(fbids):
            params[f"attached_media[{i}]"] = json.dumps({"media_fbid": fid})
        r = api("POST", f"{page_id}/feed", params)
        pid = r.get("id")
        print(f"   карусел от {len(fbids)} кадъра")
    add_comment(pid, post.get("comment"), token)
    return pid


def wait_container(cid, token, what="снимката", tries=20, pause=3):
    for _ in range(tries):
        s = api("GET", cid, {"fields": "status_code", "access_token": token})
        if s.get("status_code") == "FINISHED":
            return
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram не успя да обработи {what}.")
        time.sleep(pause)
    raise RuntimeError(f"Instagram се забави прекалено с {what}.")


def publish_instagram(post, token, ig_id):
    if post.get("video"):
        # Reel: обработката на видео отнема минути, затова чакаме по-дълго
        c = api("POST", f"{ig_id}/media", {
            "media_type": "REELS",
            "video_url": image_url(post["video"]),
            "caption": post["caption"],
            "share_to_feed": "true",
            "access_token": token,
        })
        cid = c["id"]
        wait_container(cid, token, "видеото", tries=60, pause=10)
        print("   Reel")
        r = api("POST", f"{ig_id}/media_publish", {"creation_id": cid, "access_token": token})
        mid = r.get("id")
        add_comment(mid, post.get("comment"), token)
        return mid
    imgs = images(post)
    if len(imgs) == 1:
        c = api("POST", f"{ig_id}/media",
                {"image_url": image_url(imgs[0]), "caption": post["caption"], "access_token": token})
        cid = c["id"]
        wait_container(cid, token)
    else:
        children = []
        for name in imgs:
            ch = api("POST", f"{ig_id}/media", {"image_url": image_url(name),
                                                "is_carousel_item": "true", "access_token": token})
            wait_container(ch["id"], token, "кадър от карусела")
            children.append(ch["id"])
        c = api("POST", f"{ig_id}/media", {"media_type": "CAROUSEL",
                                           "children": ",".join(children),
                                           "caption": post["caption"], "access_token": token})
        cid = c["id"]
        wait_container(cid, token, "карусела")
        print(f"   карусел от {len(children)} кадъра")
    r = api("POST", f"{ig_id}/media_publish", {"creation_id": cid, "access_token": token})
    mid = r.get("id")
    add_comment(mid, post.get("comment"), token)
    return mid


def cmd_list(posts, state):
    for p in posts:
        s = state.get(p["id"])
        mark = "✓ публикуван" if s and s.get("ok") else ("✗ грешка" if s else "· чака")
        if p.get("video"):
            kind = "видео   "
        else:
            n = len(p.get("images") or [p["image"]])
            kind = f"карусел {n}" if n > 1 else "снимка  "
        print(f'{p["when"].replace("T", " ")}  {p["platform"]:<9}  пост {p["post"]:>2}  {kind}  {mark}')


def cmd_check(posts):
    token, page_id, ig_id = env("META_PAGE_TOKEN"), env("FB_PAGE_ID"), env("IG_USER_ID")
    env("IMAGE_BASE_URL")
    page = api("GET", page_id, {"fields": "name", "access_token": token})
    print("Facebook страница:", page.get("name"))
    ig = api("GET", ig_id, {"fields": "username", "access_token": token})
    print("Instagram профил: @" + ig.get("username", "?"))
    bad = total = 0
    for p in posts:
        for name in ([p["video"]] if p.get("video") else images(p)):
            total += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(image_url(name), method="HEAD"), timeout=30) as r:
                    ctype = r.headers.get("Content-Type", "")
                    if "image" not in ctype and "video" not in ctype:
                        bad += 1; print("  не е снимка:", name, ctype)
            except Exception as e:
                bad += 1; print("  не се отваря:", name, e)
    print(f"Снимки: {total - bad} от {total} се отварят.")
    if bad:
        sys.exit(1)
    print("Всичко е наред.")


def cmd_test(posts):
    """Пробна публикация, която не се вижда от никого:
       Facebook — скрита публикация (само в Business Suite), Instagram — подготвена, но непусната."""
    token, page_id, ig_id = env("META_PAGE_TOKEN"), env("FB_PAGE_ID"), env("IG_USER_ID")
    fb = next(p for p in posts if p["platform"] == "facebook")
    ig = next(p for p in posts if p["platform"] == "instagram")

    r = api("POST", f"{page_id}/photos", {
        "url": image_url(images(fb)[0]),
        "message": "ТЕСТ на автоматичното публикуване — тази публикация е скрита и се трие.\n\n"
                   + fb["caption"],
        "published": "false",
        "access_token": token,
    })
    pid = r.get("id") or r.get("post_id")
    print("Facebook: качена СКРИТА публикация, id =", pid)
    print("  Виж я в Meta Business Suite → Съдържание → Публикации → раздел за скрити/чернови.")
    print("  Изтрий я оттам, след като я видиш.")

    c = api("POST", f"{ig_id}/media",
            {"image_url": image_url(images(ig)[0]), "caption": ig["caption"], "access_token": token})
    cid = c["id"]
    status = "?"
    for _ in range(20):
        s = api("GET", cid, {"fields": "status_code", "access_token": token})
        status = s.get("status_code", "?")
        if status in ("FINISHED", "ERROR"):
            break
        time.sleep(3)
    if status == "FINISHED":
        print("Instagram: публикацията се подготви успешно и НЕ е пусната. Всичко работи.")
        print("  (подготовката изтича сама след 24 часа — нищо не остава)")
    else:
        print("Instagram: проблем при подготовката, статус:", status)
        sys.exit(1)
    print("Тестът мина. Нищо не е излязло публично.")


def cmd_run(posts, state, dry):
    now = datetime.now(timezone.utc)
    def pending(p):
        s = state.get(p["id"]) or {}
        return not s.get("ok") and not s.get("skipped") and s.get("tries", 0) < 3
    due = [p for p in posts if pending(p) and when_utc(p) <= now]
    if not due:
        nxt = next((p for p in posts if when_utc(p) > now), None)
        print("Няма пост за публикуване." + (f' Следващ: {nxt["when"]} ({nxt["platform"]}).' if nxt else " Графикът е изпълнен."))
        return 0
    if dry:
        for p in due:
            print(f'[проба] {p["when"]} {p["platform"]} пост {p["post"]}')
        return 0
    token, page_id, ig_id = env("META_PAGE_TOKEN"), env("FB_PAGE_ID"), env("IG_USER_ID")
    failed = 0
    for p in due:
        late = now - when_utc(p)
        if late > LATE_LIMIT:
            print(f'Пропускам пост {p["post"]} ({p["platform"]}) — закъснял с {late}. Пусни го ръчно, ако още е актуален.')
            state[p["id"]] = {"ok": False, "skipped": "too_late", "at": now.isoformat()}
            continue
        try:
            pid = (publish_facebook(p, token, page_id) if p["platform"] == "facebook"
                   else publish_instagram(p, token, ig_id))
            state[p["id"]] = {"ok": True, "remote_id": pid, "at": now.isoformat()}
            print(f'Публикуван пост {p["post"]} ({p["platform"]}): {pid}')
        except Exception as e:
            failed += 1
            prev = state.get(p["id"]) or {}
            state[p["id"]] = {"ok": False, "error": str(e), "tries": prev.get("tries", 0) + 1,
                              "at": now.isoformat()}
            print(f'ГРЕШКА при пост {p["post"]} ({p["platform"]}): {e}')
        save_state(state)
    return 1 if failed else 0


def main():
    posts = load(POSTS, [])
    state = load(STATE, {})
    args = set(sys.argv[1:])
    if "--list" in args:
        cmd_list(posts, state)
    elif "--check" in args:
        cmd_check(posts)
    elif "--test" in args:
        cmd_test(posts)
    else:
        sys.exit(cmd_run(posts, state, dry="--dry-run" in args))


if __name__ == "__main__":
    main()
