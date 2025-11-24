from bs4 import BeautifulSoup
import json
import time
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import requests


class TwitterMonitor:
    def __init__(self, usernames_file='usernames.txt', storage_file='tweet_storage.json', config_file='config.json'):
        self.usernames_file = usernames_file
        self.storage_file = storage_file
        self.base_url = 'https://nitter.net'

        self.config = self.load_config(config_file)
        self.telegram_bot_token = self.config.get('telegram_bot_token', '')
        self.telegram_chat_id = self.config.get('telegram_chat_id', '')

        if not self.telegram_bot_token or self.telegram_bot_token == 'YOUR_BOT_TOKEN_HERE':
            print("⚠️ Telegram bot token не налаштовано в config.json")
        if not self.telegram_chat_id or self.telegram_chat_id == 'YOUR_CHAT_ID_HERE':
            print("⚠️ Telegram chat ID не налаштовано в config.json")

        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"🔧 Selenium Chrome драйвер ініціалізовано")
        except Exception as e:
            print(f"⚠️ Помилка ініціалізації Selenium: {e}")
            self.driver = None

        self.tweet_storage = self.load_storage()

    def load_config(self, config_file):
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Помилка при завантаженні config: {e}")
                return {}
        return {}


    def load_storage(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Помилка при завантаженні storage: {e}")
                return {}
        return {}

    def save_storage(self):
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.tweet_storage, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Помилка при збереженні storage: {e}")

    def load_usernames(self):
        if not os.path.exists(self.usernames_file):
            print(f"Файл {self.usernames_file} не знайдено!")
            return []

        with open(self.usernames_file, 'r', encoding='utf-8') as f:
            usernames = [line.strip() for line in f if line.strip()]
        return usernames

    def send_telegram_message(self, message):
        """Відправляє повідомлення в Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("  ⚠️ Telegram не налаштовано, повідомлення не відправлено")
            return False

        if self.telegram_bot_token == 'YOUR_BOT_TOKEN_HERE' or self.telegram_chat_id == 'YOUR_CHAT_ID_HERE':
            print("  ⚠️ Telegram credentials не налаштовані в config.json")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"

        payload = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print("  ✅ Повідомлення відправлено в Telegram")
                return True
            else:
                print(f"  ❌ Помилка Telegram API: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"  ❌ Помилка при відправці в Telegram: {e}")
            return False

    def fetch_user_tweets(self, username):
        if not self.driver:
            print(f"  ❌ Selenium драйвер не ініціалізовано")
            return []

        url = f"{self.base_url}/{username}"

        try:
            print(f"  🔍 Завантаження профілю...")
            self.driver.get(url)
            # Зменшуємо затримку до 2 секунд
            time.sleep(2)
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            tweet_items = soup.find_all('div', class_='timeline-item')

            tweets = []
            for item in tweet_items:
                tweet_link = item.find('a', class_='tweet-link')
                if tweet_link and 'href' in tweet_link.attrs:
                    href = tweet_link['href']
                    if '/status/' in href:
                        tweet_id = href.split('/status/')[1].split('#')[0]
                        tweet_content_div = item.find('div', class_='tweet-content')
                        tweet_content = tweet_content_div.get_text(strip=True) if tweet_content_div else ""
                        tweet_date_elem = item.find('span', class_='tweet-date')
                        tweet_date = tweet_date_elem.get_text(strip=True) if tweet_date_elem else ""

                        tweets.append({
                            'id': tweet_id,
                            'content': tweet_content,
                            'date': tweet_date,
                            'url': f"https://twitter.com/{username}/status/{tweet_id}"
                        })

            return tweets

        except Exception as e:
            print(f"  ❌ Помилка для @{username}: {e}")
            return []

    def __del__(self):
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                print("🔧 Selenium драйвер закрито")
            except:
                pass

    def check_new_tweets(self, username, tweets):
        """
        Перевіряє наявність нових твітів.
        Повертає тільки твіти, які є НОВІШИМИ за останній збережений.
        """
        if not tweets:
            return []

        latest_tweet_id = tweets[0]['id']

        # Якщо це перший раз моніторимо цього юзера - просто зберігаємо стан, нічого не надсилаємо
        if username not in self.tweet_storage:
            self.tweet_storage[username] = {
                'latest_tweet_id': latest_tweet_id,
                'all_tweet_ids': [tweet['id'] for tweet in tweets],
                'last_checked': datetime.now().isoformat()
            }
            self.save_storage()
            print(f"  📝 Додано до моніторингу. Останній твіт ID: {latest_tweet_id}")
            return []

        stored_latest_id = self.tweet_storage[username]['latest_tweet_id']
        stored_ids = set(self.tweet_storage[username]['all_tweet_ids'])

        # Якщо є новий твіт (ID відрізняється)
        if latest_tweet_id != stored_latest_id:
            # Знаходимо ТІЛЬКИ нові твіти (яких немає в stored_ids)
            new_tweets = []
            for tweet in tweets:
                if tweet['id'] not in stored_ids:
                    new_tweets.append(tweet)
                else:
                    # Як тільки знайшли знайомий твіт, зупиняємось
                    # (бо далі йдуть старіші твіти)
                    break

            # Оновлюємо storage ТІЛЬКИ новими ID
            if new_tweets:
                # Додаємо нові ID на початок списку
                new_ids = [tweet['id'] for tweet in new_tweets]
                updated_all_ids = new_ids + self.tweet_storage[username]['all_tweet_ids']

                # Зберігаємо максимум 100 останніх ID (щоб не росло безмежно)
                self.tweet_storage[username]['all_tweet_ids'] = updated_all_ids[:100]
                self.tweet_storage[username]['latest_tweet_id'] = latest_tweet_id

            self.tweet_storage[username]['last_checked'] = datetime.now().isoformat()
            self.save_storage()

            return new_tweets
        else:
            # Нічого нового, просто оновлюємо час перевірки
            self.tweet_storage[username]['last_checked'] = datetime.now().isoformat()
            self.save_storage()
            return []

    def monitor_once(self):
        usernames = self.load_usernames()
        if not usernames:
            print("Список юзернеймів порожній!")
            return
        print(f"\n{'='*60}")
        print(f"Початок перевірки - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        for username in usernames:
            print(f"Перевіряємо @{username}...")
            tweets = self.fetch_user_tweets(username)
            if not tweets:
                print(f"  ⚠️ Не вдалось отримати твіти або їх немає\n")
                # Затримка перед наступним юзером навіть при помилці
                time.sleep(2)
                continue
            print(f"  Знайдено {len(tweets)} твітів")
            new_tweets = self.check_new_tweets(username, tweets)
            if new_tweets:
                print(f"  🔔 НОВІ ТВІТИ ({len(new_tweets)}):")
                for tweet in new_tweets:
                    print(f"     ID: {tweet['id']}")
                    print(f"     Дата: {tweet['date']}")
                    print(f"     Контент: {tweet['content'][:100]}...")
                    print(f"     URL: {tweet['url']}")
                    print()

                    # Відправляємо повідомлення в Telegram
                    telegram_message = (
                        f"🔔 <b>Новий твіт від @{username}</b>\n\n"
                        f"📅 {tweet['date']}\n\n"
                        f"💬 {tweet['content']}\n\n"
                        f"🔗 <a href='{tweet['url']}'>Відкрити твіт</a>"
                    )
                    self.send_telegram_message(telegram_message)
                    time.sleep(1)
            else:
                print(f"  ✓ Нових твітів немає\n")

            # ВАЖЛИВА затримка між перевіркою кожного юзера (5 секунд)
            # Це дає час системі обробити дані і запобігає пропуску постів
            time.sleep(5)

    def monitor_continuous(self, interval=300):
        interval_min = interval / 60
        print(f"{'='*60}")
        print(f"🚀 Запуск безперервного моніторингу")
        print(f"⏱️  Інтервал: {interval} секунд ({interval_min:.1f} хв)")
        print(f"⛔ Натисніть Ctrl+C для зупинки")
        print(f"{'='*60}\n")
        try:
            while True:
                self.monitor_once()
                print(f"\n{'─'*60}")
                print(f"⏳ Наступна перевірка через {interval} секунд ({interval_min:.1f} хв)...")
                print(f"{'─'*60}\n")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n\n{'='*60}")
            print("⛔ Моніторинг зупинено користувачем")
            print(f"{'='*60}\n")

def main():
    monitor = TwitterMonitor()
    # Змінено на 60 секунд для більш стабільної роботи
    # З урахуванням 5 сек затримки між юзерами, це оптимально
    monitor.monitor_continuous(interval=60)

if __name__ == "__main__":
    main()
