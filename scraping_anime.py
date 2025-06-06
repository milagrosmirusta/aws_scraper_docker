
import sys
import os
import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import boto3

s3 = boto3.client("s3")
bucket = "anime-mal-scraper"
batch_key_prefix = "output/"

def scrap_completed_anime(user):
    url = f"https://myanimelist.net/animelist/{user}?status=2"
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=options)

    driver.get(url)
    SCROLL_PAUSE_TIME = 1.5
    last_height = driver.execute_script("return document.body.scrollHeight")

    for _ in range(30):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".list-table tbody tr"))
        )
        rows = driver.find_elements(By.CSS_SELECTOR, ".list-table tbody tr")
    except:
        print(f"❌ Timeout o error cargando tabla de {user}")
        driver.quit()
        raise Exception("No se pudo acceder a la tabla.")

    data = []
    for row in rows:
        try:
            title_link = row.find_element(By.CSS_SELECTOR, ".data.title .link")
            title = title_link.text.strip()
            href = title_link.get_attribute("href")
            anime_id = None
            if "/anime/" in href:
                parts = href.split("/")
                if len(parts) > 4:
                    try:
                        anime_id = int(parts[4])
                    except ValueError:
                        anime_id = None
            score = row.find_element(By.CSS_SELECTOR, ".data.score").text.strip()
            score = float(score) if score else None
            if not title:
                continue
            data.append({
                "user": user,
                "anime_id": anime_id,
                "title": title,
                "score": score
            })
        except:
            continue

    driver.quit()
    print(f"✅ Scrapeados {len(data)} animes para {user}")
    return pd.DataFrame(data)

def try_scrape_with_retries(user, retries=3, wait_range=(3, 7)):
    for attempt in range(1, retries + 1):
        try:
            return scrap_completed_anime(user)
        except Exception as e:
            print(f"⚠️ Intento {attempt} fallido para {user}: {e}")
            if attempt == retries:
                raise
            wait = random.uniform(*wait_range)
            print(f"🔁 Reintentando en {round(wait, 1)}s...")
            time.sleep(wait)

if __name__ == "__main__":
    print("🚀 Iniciando scraping...")
    filename = sys.argv[1]
    batch_id = os.path.basename(filename).replace(".txt", "")
    output_file = f"output/output_{batch_id}.parquet"
    error_file = f"output/errors_{batch_id}.txt"
    progress_file = f"output/progress_{batch_id}.txt"

    for key, local in [
        (f"{batch_key_prefix}{os.path.basename(output_file)}", output_file),
        (f"{batch_key_prefix}{os.path.basename(progress_file)}", progress_file),
        (f"{batch_key_prefix}{os.path.basename(error_file)}", error_file),
    ]:
        try:
            s3.download_file(bucket, key, local)
            print(f"📥 Descargado {key}")
        except Exception as e:
            print(f"⚠️ No se pudo descargar {key}: {e}")

    with open(filename, "r") as f:
        users = [line.strip() for line in f if line.strip()]
    print(f"👥 Primeros usuarios: {users[:5]}")

    done_users = set()
    if os.path.exists(progress_file):
        with open(progress_file) as pf:
            for line in pf:
                if line.startswith("DONE"):
                    done_users.add(line.split()[1])
    users = [u for u in users if u not in done_users]

    existentes = pd.read_parquet(output_file) if os.path.exists(output_file) else pd.DataFrame()
    errores = []

    for i, user in enumerate(users, 1):
        print(f"🔍 ({i}/{len(users)}) Scrappeando {user}")
        with open(progress_file, "a") as progress:
            progress.write(f"START {user} {time.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            df = try_scrape_with_retries(user)
        except Exception as e:
            errores.append(f"{user}: {e}")
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(f"{user}: {e}\n")
            continue
        if df is not None and not df.empty:
            nuevos = df.copy()
            nuevos["score"] = pd.to_numeric(nuevos["score"], errors="coerce")
            nuevos["anime_id"] = pd.to_numeric(nuevos["anime_id"], errors="coerce").astype("Int64")

            if "score" not in existentes.columns:
                existentes["score"] = pd.Series(dtype='float')
            else:
                existentes["score"] = pd.to_numeric(existentes["score"], errors="coerce")
            if "anime_id" not in existentes.columns:
                existentes["anime_id"] = pd.Series(dtype='Int64')
            else:
                existentes["anime_id"] = pd.to_numeric(existentes["anime_id"], errors="coerce").astype("Int64")

            existentes = pd.concat([existentes, nuevos]).drop_duplicates(subset=["user", "anime_id"])
            existentes.to_parquet(output_file, index=False)
            print(f"💾 Guardado con {len(existentes)} registros")

            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(f"DONE {user} {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        with open(error_file, "w", encoding="utf-8") as f:
            f.write("\n".join(errores))

        s3.upload_file(output_file, bucket, f"{batch_key_prefix}{os.path.basename(output_file)}")
        s3.upload_file(progress_file, bucket, f"{batch_key_prefix}{os.path.basename(progress_file)}")
        s3.upload_file(error_file, bucket, f"{batch_key_prefix}{os.path.basename(error_file)}")
        print("☁️ Subida a S3 completa.")