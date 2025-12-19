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
    
    # FIX FOR STREAMLIT CLOUD (Standard Linux Path)
    chrome_options.binary_location = "/usr/bin/chromium"

    # User Agent to mimic a real laptop
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Driver Service Setup
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_soup(url):
    """Fetches the URL using Selenium."""
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
    """Extracts top keywords/search terms from text."""
    if not text:
        return []
    try:
        r = Rake()
        r.extract_keywords_from_text(text)
        # Return top 15 phrases for better "Search Term" coverage
        return list(set(r.get_ranked_phrases()[:15]))
    except:
        return []

# --- SCRAPING LOGIC ---

def get_meta_content(soup, property_name):
    tag = soup.find("meta", property=property_name)
    return tag['content'] if tag else None

def scrape_amazon(soup):
    data = {}
    
    # 1. Title
    try:
        data['title'] = soup.find("span", id="productTitle").text.strip()
    except:
        data['title'] = get_meta_content(soup, "og:title")

    # 2. Bullet Points (Features)
    try:
        # Try finding the specific unordered list for feature bullets
        bullet_section = soup.find("div", id="feature-bullets")
        if bullet_section:
            bullets = bullet_section.find_all("li")
            # Clean text and remove "show more" hidden items
            data['bullets'] = [b.text.strip() for b in bullets if not "a-declarative" in b.get('class', [])]
        else:
            data['bullets'] = []
    except:
        data['bullets'] = []

    # 3. Description (Fallback if bullets fail, or full text)
    try:
        # Join bullets for a full description text
        if data['bullets']:
            data['description'] = " ".join(data['bullets'])
        else:
            # Fallback to meta description
            data['description'] = get_meta_content(soup, "og:description")
    except:
        data['description'] = ""

    # 4. Image
    try:
        img_div = soup.find("div", id="imgTagWrapperId")
        data['image_url'] = img_div.find("img")['src']
    except:
        data['image_url'] = get_meta_content(soup, "og:image")

    # 5. Review Snippet
    try:
        data['review'] = soup.find("div", {"data-hook": "review-collapsed"}).text.strip()
    except:
        data['review'] = "Top review not accessible."
        
    return data

def scrape_generic(soup):
    # Fallback for Flipkart/Meesho if specific scrapers break
    return {
        'title': get_meta_content(soup, "og:title") or "Title not found",
        'description': get_meta_content(soup, "og:description") or "No description",
        'bullets': [], # Generic sites might not have standard bullets
        'image_url': get_meta_content(soup, "og:image"),
        'review': "Reviews not available."
    }

# --- APP UI ---
st.set_page_config(page_title="Pro Scraper", layout="wide")
st.title("🛒 Amazon/Flipkart/Meesho Scraper")

url = st.text_input("Paste Product URL:")

if st.button("Scrape Data"):
    if not url:
        st.warning("Please paste a URL first.")
    else:
        with st.spinner("Scraping..."):
            soup = get_soup(url)
            
            if soup:
                if "amazon" in url:
                    data = scrape_amazon(soup)
                else:
                    data = scrape_generic(soup)

                st.divider()
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if data.get('image_url'):
                        st.image(data['image_url'], width=300)
                        try:
                            response = requests.get(data['image_url'])
                            st.download_button(
                                label="Download Image",
                                data=response.content,
                                file_name="product.jpg",
                                mime="image/jpeg"
                            )
                        except:
                            pass

                with col2:
                    st.subheader(data.get('title'))
                    
                    # --- BULLET POINTS SECTION ---
                    if data.get('bullets'):
                        st.markdown("### Product Features (Bullet Points)")
                        for bullet in data['bullets']:
                            st.markdown(f"- {bullet}")
                    else:
                        st.markdown("### Description")
                        st.write(data.get('description'))

                    st.info(f"**Top Review:** {data.get('review')}")
                    
                    # --- SEARCH TERMS SECTION ---
                    st.markdown("### 🔍 Search Terms / Keywords")
                    # Combine Title + Bullets to generate rich search terms
                    full_text = str(data.get('title')) + " " + " ".join(data.get('bullets', []))
                    keywords = extract_keywords(full_text)
                    
                    # Display as tags
                    st.write(", ".join([f"`{k}`" for k in keywords]))

                # CSV Export
                # We join bullets with a separator for the CSV so it stays in one cell
                csv_data = data.copy()
                csv_data['bullets'] = " | ".join(data.get('bullets', []))
                
                df = pd.DataFrame([csv_data])
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV", csv, "data.csv", "text/csv")
