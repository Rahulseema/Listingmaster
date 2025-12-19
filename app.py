import streamlit as st
from bs4 import BeautifulSoup
import pandas as pd
from rake_nltk import Rake
from io import BytesIO
import time
import random
import requests
import nltk

# --- SELENIUM IMPORTS ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- SETUP NLTK (Runs once to ensure keyword extractor works) ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', quiet=True)

# --- CONFIGURATION ---
def get_driver():
    """Sets up a headless Chrome browser to mimic a real user."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run without a visible UI
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Crucial: User Agent makes us look like a standard Windows laptop
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_soup(url):
    """Fetches the URL using Selenium and returns a BeautifulSoup object."""
    driver = None
    try:
        driver = get_driver()
        driver.get(url)
        
        # Human-like pause (3-5 seconds)
        time.sleep(random.uniform(3, 5))
        
        # Scroll down to trigger lazy loading of images
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
        # Return top 10 unique phrases
        return list(set(r.get_ranked_phrases()[:10]))
    except:
        return ["Could not extract keywords"]

# --- PLATFORM SPECIFIC SCRAPERS ---

def get_meta_content(soup, property_name):
    """Helper to safely get meta tag content (OpenGraph)."""
    tag = soup.find("meta", property=property_name)
    return tag['content'] if tag else None

def scrape_generic(soup):
    """Fallback scraper using OpenGraph tags (Works on most sites)."""
    return {
        'title': get_meta_content(soup, "og:title") or soup.title.string,
        'description': get_meta_content(soup, "og:description") or "No description found",
        'image_url': get_meta_content(soup, "og:image"),
        'review': "Reviews require specific scraping logic."
    }

def scrape_amazon(soup):
    data = {}
    # 1. Title
    try:
        data['title'] = soup.find("span", id="productTitle").text.strip()
    except:
        data['title'] = get_meta_content(soup, "og:title")

    # 2. Description
    try:
        bullets = soup.find("div", id="feature-bullets").find_all("li")
        data['description'] = " ".join([b.text.strip() for b in bullets])
    except:
        data['description'] = get_meta_content(soup, "og:description")

    # 3. Image
    try:
        img_div = soup.find("div", id="imgTagWrapperId")
        data['image_url'] = img_div.find("img")['src']
    except:
        data['image_url'] = get_meta_content(soup, "og:image")

    # 4. Review
    try:
        # Tries to find the first review body
        data['review'] = soup.find("div", {"data-hook": "review-collapsed"}).text.strip()
    except:
        data['review'] = "Top review not accessible via quick scrape."
        
    return data

def scrape_flipkart(soup):
    data = {}
    # 1. Title
    try:
        # Tries standard class, then H1
        data['title'] = soup.find("span", class_="B_NuCI").text.strip()
    except:
        try:
             data['title'] = soup.find("h1").text.strip()
        except:
             data['title'] = get_meta_content(soup, "og:title")

    # 2. Description
    try:
        data['description'] = soup.find("div", class_="_1mXcCf").text.strip()
    except:
        data['description'] = get_meta_content(soup, "og:description")

    # 3. Image
    try:
        # Flipkart images are tricky, often uses styling. Fallback to OG is safest.
        data['image_url'] = get_meta_content(soup, "og:image")
    except:
        data['image_url'] = None

    # 4. Review
    try:
        data['review'] = soup.find("div", class_="t-ZTKy").text.strip().replace("READ MORE", "")
    except:
        data['review'] = "No top review found."

    return data

def scrape_meesho(soup):
    # Meesho class names are randomized (e.g., 'sc-eDvSVe').
    # It is MUCH safer to rely on OpenGraph tags for Meesho.
    data = scrape_generic(soup)
    data['review'] = "Meesho reviews require login/selenium interaction."
    return data

# --- STREAMLIT APP UI ---
st.set_page_config(page_title="Product Scraper", layout="wide")

st.title("🛒 E-Commerce Scraper (Selenium Enabled)")
st.markdown("Paste a product link from **Amazon**, **Flipkart**, or **Meesho**.")

url = st.text_input("Product URL:")

if st.button("Scrape Product"):
    if not url:
        st.warning("Please paste a URL first.")
    else:
        with st.spinner("Starting Chrome Driver & Fetching Data..."):
            soup = get_soup(url)
            
            if soup:
                # Determine scraper based on URL
                if "amazon" in url:
                    st.success("Detected: Amazon")
                    data = scrape_amazon(soup)
                elif "flipkart" in url:
                    st.success("Detected: Flipkart")
                    data = scrape_flipkart(soup)
                elif "meesho" in url:
                    st.success("Detected: Meesho")
                    data = scrape_meesho(soup)
                else:
                    st.info("URL not recognized, trying generic scrape...")
                    data = scrape_generic(soup)

                # --- DISPLAY RESULTS ---
                st.divider()
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if data.get('image_url'):
                        st.image(data['image_url'], width=300)
                        
                        # Download Button
                        try:
                            response = requests.get(data['image_url'])
                            st.download_button(
                                label="Download Image",
                                data=response.content,
                                file_name="product_image.jpg",
                                mime="image/jpeg"
                            )
                        except:
                            st.error("Could not prepare download.")
                    else:
                        st.write("No Image Found")

                with col2:
                    st.subheader(data.get('title', 'No Title'))
                    
                    st.markdown("#### Description")
                    desc = data.get('description', '')
                    if desc:
                        st.write(desc[:500] + "..." if len(desc) > 500 else desc)
                    else:
                        st.write("No description found.")

                    st.markdown("#### Keywords (SEO)")
                    keywords = extract_keywords(str(data.get('title', '')) + " " + str(data.get('description', '')))
                    st.code(", ".join(keywords))

                    st.markdown("#### Top Review Snippet")
                    st.info(data.get('review', 'No reviews found'))

                # CSV Download
                df = pd.DataFrame([data])
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Data as CSV",
                    csv,
                    "scraped_data.csv",
                    "text/csv"
                )
