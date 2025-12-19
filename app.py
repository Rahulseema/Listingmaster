import streamlit as st
from bs4 import BeautifulSoup
import pandas as pd
from rake_nltk import Rake
from io import BytesIO
import time
import random
import requests
import nltk
import os
import re

# --- SELENIUM IMPORTS ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- SETUP NLTK ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

# --- CONFIGURATION ---
def get_driver():
    """Sets up a headless Chrome browser optimized for Streamlit Cloud."""
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = "/usr/bin/chromium" # Streamlit Cloud Path
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_soup(url):
    driver = None
    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(random.uniform(2, 4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(1)
        return BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def extract_keywords(text):
    if not text: return []
    try:
        r = Rake()
        r.extract_keywords_from_text(text)
        # Return top 20 keywords for SEO
        return list(set(r.get_ranked_phrases()[:20]))
    except:
        return []

def clean_price(price_str):
    """Removes currency symbols and text to return just the number string."""
    if not price_str: return "N/A"
    # Keep only digits and dots
    return re.sub(r'[^\d.]', '', price_str)

# --- AMAZON SCRAPER ---
def scrape_amazon(soup):
    data = {}
    
    # 1. Title
    try: data['title'] = soup.find("span", id="productTitle").text.strip()
    except: data['title'] = "Title Not Found"

    # 2. Price (Selling & MRP)
    try:
        # Selling Price
        price_whole = soup.find("span", class_="a-price-whole")
        data['selling_price'] = clean_price(price_whole.text) if price_whole else "N/A"
        
        # MRP (formatted usually as strike-through text)
        mrp_span = soup.find("span", class_="a-text-price")
        if mrp_span:
            data['mrp'] = clean_price(mrp_span.find("span", class_="a-offscreen").text)
        else:
            data['mrp'] = "N/A"
    except:
        data['selling_price'] = "N/A"
        data['mrp'] = "N/A"

    # 3. Bullet Points
    data['bullets'] = []
    try:
        bullet_section = soup.find("div", id="feature-bullets")
        if bullet_section:
            bullets = bullet_section.find_all("li")
            data['bullets'] = [b.text.strip() for b in bullets if not "a-declarative" in b.get('class', [])]
    except: pass

    # 4. Description
    try:
        # Sometimes description is in different divs
        desc_div = soup.find("div", id="productDescription")
        data['description'] = desc_div.text.strip() if desc_div else " ".join(data['bullets'])
    except:
        data['description'] = ""

    # 5. Variants (Sizes/Colors)
    variants = []
    try:
        # Look for variation headers
        variation_divs = soup.find_all("div", id=lambda x: x and x.startswith("variation_"))
        for div in variation_divs:
            label = div.find("label", class_="a-form-label")
            label_text = label.text.strip().replace(":", "") if label else "Option"
            
            # Get text of options
            options = div.find_all("li")
            option_texts = [opt.text.strip() for opt in options]
            # Clean up empty strings
            option_texts = [o for o in option_texts if o]
            
            if option_texts:
                variants.append(f"{label_text}: {', '.join(option_texts)}")
    except: pass
    data['variants'] = " | ".join(variants) if variants else "No specific variants detected"

    # 6. Image & Review
    try:
        data['image_url'] = soup.find("div", id="imgTagWrapperId").find("img")['src']
    except: data['image_url'] = None
    
    try:
        data['review'] = soup.find("div", {"data-hook": "review-collapsed"}).text.strip()
    except: data['review'] = "N/A"

    return data

# --- FLIPKART SCRAPER ---
def scrape_flipkart(soup):
    data = {}
    
    # 1. Title
    try: data['title'] = soup.find("span", class_="B_NuCI").text.strip()
    except: 
        try: data['title'] = soup.find("h1").text.strip()
        except: data['title'] = "Title Not Found"

    # 2. Price
    try:
        data['selling_price'] = clean_price(soup.find("div", class_="_30jeq3").text)
        mrp_tag = soup.find("div", class_="_3I9_wc")
        data['mrp'] = clean_price(mrp_tag.text) if mrp_tag else "N/A"
    except:
        data['selling_price'] = "N/A"; data['mrp'] = "N/A"

    # 3. Description / Highlights (Bullets)
    data['bullets'] = []
    try:
        # Flipkart "Highlights" are their bullet points
        highlights = soup.find_all("li", class_="_21Ahn-")
        data['bullets'] = [h.text.strip() for h in highlights]
        
        # Main Description
        desc_div = soup.find("div", class_="_1mXcCf")
        data['description'] = desc_div.text.strip() if desc_div else " ".join(data['bullets'])
    except: 
        data['description'] = ""

    # 4. Variants (Colors/Storage)
    variants = []
    try:
        # Flipkart often lists variants in tables or specific divs
        # Color selection row
        color_divs = soup.find_all("div", class_="_2C41yO")
        # This is hard on Flipkart as they change classes often, strictly experimental
        if color_divs:
            variants.append("Colors/Versions available (Check link)")
    except: pass
    data['variants'] = " | ".join(variants) if variants else "Check link for options"

    # 5. Image & Review
    try: data['image_url'] = soup.find("img", class_="_396cs4")['src']
    except: data['image_url'] = None
    
    try: data['review'] = soup.find("div", class_="t-ZTKy").text.strip().replace("READ MORE", "")
    except: data['review'] = "N/A"

    return data

# --- GENERIC / MEESHO SCRAPER ---
def scrape_generic(soup):
    # Meesho is React-based and very dynamic. 
    # Reliable scraping requires targeting specific randomly generated classes 
    # which change weekly. We stick to OpenGraph for stability.
    def get_meta(prop):
        t = soup.find("meta", property=prop)
        return t['content'] if t else None

    return {
        'title': get_meta("og:title") or "Title Not Found",
        'selling_price': "N/A", # Hard to get reliably on generic scrape
        'mrp': "N/A",
        'bullets': ["Generic scrape does not support bullet points"],
        'description': get_meta("og:description") or "",
        'variants': "N/A",
        'image_url': get_meta("og:image"),
        'review': "N/A"
    }

# --- APP UI ---
st.set_page_config(page_title="Ultra Scraper", layout="wide")
st.title("🛒 Ultimate Product Scraper")
st.markdown("Extracts: **Title, Price, MRP, Variants, Bullets, Keywords**")

url = st.text_input("Paste Product URL (Amazon/Flipkart):")

if st.button("Scrape Data"):
    if not url:
        st.warning("Please paste a URL.")
    else:
        with st.spinner("Analyzing Product Page..."):
            soup = get_soup(url)
            
            if soup:
                if "amazon" in url:
                    data = scrape_amazon(soup)
                    st.success("Scraped Amazon Data")
                elif "flipkart" in url:
                    data = scrape_flipkart(soup)
                    st.success("Scraped Flipkart Data")
                else:
                    data = scrape_generic(soup)
                    st.warning("Generic Scrape (Some fields may be missing)")

                # --- UI DISPLAY ---
                st.divider()
                
                # Header Section: Title & Prices
                st.header(data.get('title'))
                
                p_col1, p_col2, p_col3 = st.columns(3)
                with p_col1: st.metric("Selling Price", f"₹{data.get('selling_price')}")
                with p_col2: st.metric("MRP", f"₹{data.get('mrp')}")
                with p_col3: st.caption(f"Variants: {data.get('variants')}")

                # Content Section
                c_col1, c_col2 = st.columns([1, 2])
                
                with c_col1:
                    if data.get('image_url'):
                        st.image(data['image_url'], width=300)
                        try:
                            r = requests.get(data['image_url'])
                            st.download_button("Download Image", r.content, "img.jpg", "image/jpeg")
                        except: pass
                    else: st.info("No Image")

                with c_col2:
                    if data.get('bullets'):
                        st.subheader("Bullet Points")
                        for b in data['bullets']:
                            st.markdown(f"- {b}")
                    
                    st.subheader("Description")
                    st.write(data.get('description')[:500] + "..." if len(data.get('description')) > 500 else data.get('description'))
                    
                    st.subheader("Generated Search Keywords")
                    # SEO Logic: Combine Title + Bullets for best keywords
                    full_text = f"{data.get('title')} {' '.join(data.get('bullets', []))}"
                    keywords = extract_keywords(full_text)
                    st.write(", ".join([f"`{k}`" for k in keywords]))

                # CSV Export (Flattening the list data)
                csv_data = data.copy()
                csv_data['bullets'] = " | ".join(data.get('bullets', []))
                # Add keywords to CSV
                csv_data['search_keywords'] = ", ".join(keywords)
                
                df = pd.DataFrame([csv_data])
                st.download_button(
                    "Download Complete CSV",
                    df.to_csv(index=False).encode('utf-8'),
                    "product_data.csv",
                    "text/csv"
                )
