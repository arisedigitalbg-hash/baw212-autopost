# BAW 212 България — автоматично публикуване за октомври

40 поста (20 Facebook + 20 Instagram) излизат сами, по часовете от графика.
Безплатно: GitHub пуска скрипта на всеки 15 минути, Meta Graph API публикува.
Нищо не се въвежда на ръка.

**Настройката се прави веднъж — около час. После не пипаш нищо до края на октомври.**

---

## Стъпка 1 — GitHub хранилище (10 мин)

1. Направи безплатен профил на github.com, ако нямаш.
2. **New repository** → име `baw212-autopost` → **Public** → Create.
3. **Add file → Upload files** и провлачи **цялото съдържание** на тази папка:
   `images/`, `.github/`, `posts.json`, `publish.py`, `README.md`.
   Провери след качването, че папката `.github/workflows/` е там (понякога Windows я крие — ако липсва,
   създай я с **Add file → Create new file** и име `.github/workflows/publish.yml`, после постави съдържанието).
4. **Settings → Pages** → Source: **Deploy from a branch** → `main` / `(root)` → Save.
   След минута горе пише адрес като `https://ТВОЕТО-ИМЕ.github.io/baw212-autopost/`.
   Това е **IMAGE_BASE_URL**. Провери го: `…/images/baw212-01-hero-fb.jpg` трябва да отваря снимка.

## Стъпка 2 — достъп до Meta (30 мин)

Прави го **човек, който е администратор на Facebook страницата** на BAW 212 България
(ти, ако приятелят ти те е добавил като администратор).

1. developers.facebook.com → **My Apps → Create App** → тип **Business** → име `BAW212 Autopost`.
   Приложението остава в режим за разработка — не трябва одобрение от Meta, щом го ползва администратор на приложението.
2. **Tools → Graph API Explorer** → избери приложението → **User Token** → добави разрешенията:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `instagram_basic`, `instagram_content_publish`, `business_management` → **Generate Access Token** и потвърди.
3. Натисни **i** до токена → **Open in Access Token Tool** → **Extend Access Token**. Копирай дългия токен.
4. Обратно в Graph API Explorer, постави дългия токен и изпълни `me/accounts`.
   При страницата на BAW 212 копирай:
   - `id` → това е **FB_PAGE_ID**
   - `access_token` → това е **META_PAGE_TOKEN** (токен на страницата — не изтича, докато не смениш паролата или не махнеш достъпа)
5. Изпълни `ТВОЯТ_FB_PAGE_ID?fields=instagram_business_account`.
   Числото в `id` → **IG_USER_ID**.
   Ако няма `instagram_business_account`, Instagram профилът не е Business или не е свързан със страницата — оправи това първо.

## Стъпка 3 — въвеждане в GitHub (5 мин)

В хранилището: **Settings → Secrets and variables → Actions**

- раздел **Secrets** → New repository secret: `META_PAGE_TOKEN` = токенът на страницата
- раздел **Variables** → New repository variable:
  - `FB_PAGE_ID`
  - `IG_USER_ID`
  - `IMAGE_BASE_URL` (без наклонена черта накрая)

Токенът е таен — **не го пращай в чат и не го слагай във файл**. Само в Secrets.

## Стъпка 4 — проверка (2 мин)

**Actions → Публикуване BAW 212 → Run workflow** → mode: `check`.
Трябва да видиш името на страницата, Instagram профила и „Снимки: 40 от 40 се отварят. Всичко е наред.“

Готово. От 1 октомври в 09:30 постовете излизат сами.

---

## Как се следи

- **Actions** показва всяко пускане. Зелено = наред, червено = нещо се е объркало (пише какво).
- Файлът `state.json` се обновява след всеки публикуван пост — там са ID-тата на публикациите.
- GitHub понякога закъснява с 5–20 минути в натоварени часове. Постът за 09:30 може да излезе в 09:45.

## Ако трябва промяна

- **Друг текст или час:** редактираш поста в `posts.json` направо в GitHub (молив горе вдясно) → Commit.
- **Спиране на всичко:** Actions → Публикуване BAW 212 → „…“ → **Disable workflow**.
- **Грешка при пост:** скриптът опитва до 3 пъти. Ако постът е закъснял с повече от 12 часа, не се пуска сам — за да не излезе нещо неуместно в неподходящ момент.

## Важно

- **Не планирай същите постове и в Meta Business Suite** — ще излязат два пъти.
- Всички часове в `posts.json` са по българско време. Смяната към зимно време на 25 октомври е отчетена.
