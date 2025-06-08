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
from io import StringIO, BytesIO

# Parámetros
bucket = "anime-mal-scraper"
batch_key_prefix = "output/"
users_prefix = "users/"
s3 = boto3.client("s3")

def scrap_completed_anime(user):
    # Configura Selenium
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
        driver.quit()
        raise Exception("No se pudo acceder a la tabla.")

    data = []
    for row in rows:
        try:
            title_link = row.find_element(By.CSS_SELECTOR, ".data.title .link")
            title = title_link.text.strip()
            href = title_link.get_attribute("href")
            anime_id = int(href.split("/")[4]) if "/anime/" in href else None
            score = row.find_element(By.CSS_SELECTOR, ".data.score").text.strip()
            score = float(score) if score else None
            if not title:
                continue
            data.append({"user": user, "anime_id": anime_id, "title": title, "score": score})
        except:
            continue

    driver.quit()
    return pd.DataFrame(data)

def try_scrape_with_retries(user, retries=3, wait_range=(3, 7)):
    for attempt in range(1, retries + 1):
        try:
            return scrap_completed_anime(user)
        except Exception as e:
            print(f"❌ Intento {attempt} fallido para {user}: {e}")
            if attempt == retries:
                raise
            wait = random.uniform(*wait_range)
            print(f"🔁 Reintentando en {round(wait, 1)}s...")
            time.sleep(wait)

if __name__ == "__main__":
    filename = sys.argv[1]  # ejemplo: users_1.txt
    s3_path = f"users/{filename}"
    obj = s3.get_object(Bucket=bucket, Key=s3_path)
    users = [line.strip() for line in obj['Body'].read().decode("utf-8").splitlines() if line.strip()]
    batch_id = os.path.basename(filename).replace(".txt", "")
    output_file = f"output_{batch_id}.parquet"
    error_file = f"errors_{batch_id}.txt"
    progress_file = f"progress_{batch_id}.txt"

    # Descargar output, progress y errors si existen
    for key in [output_file, progress_file, error_file]:
        try:
            s3.download_file(bucket, f"{batch_key_prefix}{key}", key)
            print(f"📥 Descargado {key}")
        except:
            print(f"⚠️ No existe {key} en S3. Se creará desde cero.")

    # Leer users desde S3
    users_obj = s3.get_object(Bucket=bucket, Key=f"{users_prefix}{filename}")
    users = [line.strip() for line in users_obj['Body'].read().decode("utf-8").splitlines() if line.strip()]

    # Leer progress desde S3 (ya scrappeados)
    done_users = set()
    try:
        progress_obj = s3.get_object(Bucket=bucket, Key=f"{batch_key_prefix}{progress_file}")
        done_users = set(line.strip().lower() for line in progress_obj['Body'].read().decode("utf-8").splitlines())
    except:
        print("📁 No se encontró progress previo, comenzando desde cero.")

    # Filtrar usuarios restantes
    users = [u for u in users if u.lower() not in done_users]
    print(f"👥 Usuarios restantes: {len(users)}")

    existentes = pd.read_parquet(output_file) if os.path.exists(output_file) else pd.DataFrame()
    errores = []

    for i, user in enumerate(users, 1):
        print(f"🔍 ({i}/{len(users)}) Scrappeando {user}")
        try:
            df = try_scrape_with_retries(user)
        except Exception as e:
            errores.append(f"{user}: {e}")
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(f"{user}: {e}\n")
            continue

        if df is not None and not df.empty:
            df["score"] = pd.to_numeric(df["score"], errors="coerce")
            df["anime_id"] = pd.to_numeric(df["anime_id"], errors="coerce").astype("Int64")
            existentes = pd.concat([existentes, df]).drop_duplicates(subset=["user", "anime_id"])
            existentes.to_parquet(output_file, index=False)

            # Append al progress
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(f"{user}\n")

            s3.upload_file(progress_file, bucket, f"{batch_key_prefix}{progress_file}")

        # Subir archivos actualizados
        s3.upload_file(output_file, bucket, f"{batch_key_prefix}{output_file}")
        s3.upload_file(progress_file, bucket, f"{batch_key_prefix}{progress_file}")
        with open(error_file, "w", encoding="utf-8") as f:
            f.write("\n".join(errores))
        s3.upload_file(error_file, bucket, f"{batch_key_prefix}{error_file}")

        print("☁️ Archivos subidos a S3")

