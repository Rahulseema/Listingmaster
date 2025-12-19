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

# --- SELENIUM IMPORTS ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- SETUP NLTK ---
# This ensures keywords can be generated without crashing
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
    
    # 1. FIX FOR ERROR 127: Point to the installed Chromium browser
    chrome_options.binary_location = "/usr/bin/chromium"

    # 2. Add headers to look like a real user
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # 3. Service Setup
    # On Streamlit Cloud, the driver is usually at /usr/bin/chromedriver
    # We try that first, otherwise fallback to webdriver_manager
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_soup(url):
    """Fetches the URL using Selenium and returns a BeautifulSoup object."""
    driver = None
    try:
        driver = get_driver()
        driver.get(url)
        
        # Human-like pause 
        time.sleep(random.uniform(2, 4))
        
        # Scroll to load dynamic content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(1)
        
        page_source = driver.page_source
        return BeautifulSoup(page_source, "html.parser")
        
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def extract_keywords(text):
    """Extracts top keywords from text."""
    if not text:
        return []
    try:
        r = Rake()
        r.extract_keywords_from_text(text)
        return list(set(r.get_ranked_phrases()[:10]))
    except:
        return []

# --- SCRAPING LOGIC ---

def get_meta_content(soup, property_name):
    tag = soup.find("meta", property=property_name)
    return tag['content'] if tag else None

def scrape_generic(soup):
    return {
        'title': get_meta_content(soup, "og:title") or "Title not found",
        'description': get_meta_content(soup, "og:description") or "No description",
        'image_url': get_meta_content(soup, "og:image"),
        'review': "Generic scrape: Reviews not available."
    }

def scrape_amazon(soup):
    data = {}
    try:
        data['title'] = soup.find("span", id="productTitle").text.strip()
    except:
        data['title'] = get_meta_content(soup, "og:title")

    try:
        bullets = soup.find("div", id="feature-bullets").find_all("li")
        data['description'] = " ".join([b.text.strip() for b in bullets])
    except:
        data['description'] = get_meta_content(soup, "og:description")

    try:
        img_div = soup.find("div", id="imgTagWrapperId")
        data['image_url'] = img_div.find("img")['src']
    except:
        data['image_url'] = get_meta_content(soup, "og:image")

    try:
        data['review'] = soup.find("div", {"data-hook": "review-collapsed"}).text.strip()
    except:
        data['review'] = "Top review not accessible."
    return data

def scrape_flipkart(soup):
    data = {}
    try:
        data['title'] = soup.find("span", class_="B_NuCI").text.strip()
    except:
        try:
             data['title'] = soup.find("h1").text.strip()
        except:
             data['title'] = get_meta_content(soup, "og:title")

    try:
        data['description'] = soup.find("div", class_="_1mXcCf").text.strip()
    except:
        data['description'] = get_meta_content(soup, "og:description")

    try:
        data['image_url'] = get_meta_content(soup, "og:image")
    except:
        data['image_url'] = None

    try:
        data['review'] = soup.find("div", class_="t-ZTKy").text.strip().replace("READ MORE", "")
    except:
        data['review'] = "No top review found."
    return data

# --- APP UI ---
st.set_page_config(page_title="Product Scraper", layout="wide")
st.title("🛒 E-Commerce Scraper")

url = st.text_input("Paste Product URL (Amazon, Flipkart, Meesho):")

if st.button("Scrape Data"):
    if not url:
        st.warning("Please paste a URL first.")
    else:
        with st.spinner("Initializing Scraper..."):
            soup = get_soup(url)
            
            if soup:
                if "amazon" in url:
                    data = scrape_amazon(soup)
                elif "flipkart" in url:
                    data = scrape_flipkart(soup)
                elif "meesho" in url:
                    data = scrape_generic(soup) # Meesho works best with generic OG tags
                else:
                    data = scrape_generic(soup)

                st.divider()
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if data.get('image_url'):
                        st.image(data['image_url'], width=300)
                        try:
                            # Direct download logic
                            response = requests.get(data['image_url'])
                            st.download_button(
                                label="Download Image",
                                data=response.content,
                                file_name="product.jpg",
                                mime="image/jpeg"
                            )
                        except:
                            pass
                    else:
                        st.info("No Image")

                with col2:
                    st.subheader(data.get('title'))
                    st.write(data.get('description'))
                    st.info(f"Review Snippet: {data.get('review')}")
                    
                    st.markdown("#### Keywords")
                    keywords = extract_keywords(str(data.get('title')) + " " + str(data.get('description')))
                    st.success(", ".join(keywords))

                # CSV Export
                df = pd.DataFrame([data])
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV", csv, "data.csv", "text/csv")
