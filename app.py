import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from rake_nltk import Rake
from io import BytesIO
import time
import random

# --- CONFIGURATION ---
# Headers are crucial to avoid being detected as a bot immediately.
HEADERS = ({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US, en;q=0.5'
})

def get_soup(url):
    """Fetches the URL and returns a BeautifulSoup object."""
    try:
        # Random sleep to mimic human behavior
        time.sleep(random.uniform(1, 3))
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return BeautifulSoup(response.content, "html.parser")
        else:
            st.error(f"Failed to retrieve page. Status code: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None

def extract_keywords(text):
    """Extracts keywords using RAKE (Rapid Automatic Keyword Extraction)."""
    if not text:
        return []
    r = Rake()
    r.extract_keywords_from_text(text)
    return r.get_ranked_phrases()[:10] # Return top 10 keywords

def scrape_amazon(soup):
    """Scraping logic for Amazon."""
    data = {}
    
    # 1. Title
    try:
        data['title'] = soup.find("span", attrs={"id": 'productTitle'}).text.strip()
    except:
        data['title'] = "Title not found"

    # 2. Description (Bullet points)
    try:
        bullets = soup.find("div", attrs={"id": "feature-bullets"}).find_all("li")
        data['description'] = "\n".join([b.text.strip() for b in bullets])
    except:
        data['description'] = "Description not found"

    # 3. Images (Primary image)
    try:
        img_div = soup.find("div", attrs={"id": "imgTagWrapperId"})
        data['image_url'] = img_div.find("img")['src']
    except:
        # Fallback to OG tag
        try:
            data['image_url'] = soup.find("meta", property="og:image")['content']
        except:
            data['image_url'] = None

    # 4. Review (Top review)
    try:
        review = soup.find("div", {"data-hook": "review-collapsed"}).text.strip()
        data['review'] = review
    except:
        data['review'] = "Reviews difficult to access without Selenium."

    return data

def scrape_flipkart(soup):
    """Scraping logic for Flipkart."""
    data = {}
    
    # 1. Title (Class names like 'B_NuCI' change often! Check Inspect Element)
    try:
        # Common Flipkart Title Classes: B_NuCI, _35KyD6
        data['title'] = soup.find("span", class_="B_NuCI").text.strip()
    except:
        try:
            data['title'] = soup.find("h1").text.strip()
        except:
             data['title'] = "Title not found"

    # 2. Description
    try:
        # Usually in a div with class '_1mXcCf' or similar
        desc_div = soup.find("div", class_="_1mXcCf") 
        data['description'] = desc_div.text.strip() if desc_div else "Description not found"
    except:
        data['description'] = "Description not found"

    # 3. Images
    try:
        # Flipkart often loads high-res images dynamically, but we can catch the main thumbnail
        img_tag = soup.find("img", class_="_396cs4") 
        data['image_url'] = img_tag['src']
    except:
         data['image_url'] = None

    # 4. Reviews
    try:
        review = soup.find("div", class_="t-ZTKy").text.strip()
        data['review'] = review.replace("READ MORE", "")
    except:
        data['review'] = "No top review found"

    return data

def scrape_meesho(soup):
    """Scraping logic for Meesho."""
    data = {}
    
    # Meesho relies heavily on styled-components (random classes like sc-eDvSVe).
    # Strategy: Use Meta Tags (OpenGraph) as they are cleaner on Meesho.
    
    try:
        data['title'] = soup.find("meta", property="og:title")['content']
    except:
        data['title'] = "Title not found"

    try:
        data['description'] = soup.find("meta", property="og:description")['content']
    except:
        data['description'] = "Description not found"
        
    try:
        data['image_url'] = soup.find("meta", property="og:image")['content']
    except:
        data['image_url'] = None
        
    data['review'] = "Meesho reviews are dynamic and require Selenium to scrape."
    
    return data

# --- STREAMLIT APP ---
st.set_page_config(page_title="E-Com Scraper", layout="wide")

st.title("🛒 Universal Product Scraper")
st.markdown("Supports: **Amazon | Flipkart | Meesho**")

url = st.text_input("Paste Product URL here:")

if st.button("Scrape Data"):
    if not url:
        st.warning("Please enter a URL.")
    else:
        with st.spinner("Scraping data... (This might take a moment)"):
            soup = get_soup(url)
            
            if soup:
                # Detect Platform
                if "amazon" in url:
                    st.success("Detected Platform: Amazon")
                    data = scrape_amazon(soup)
                elif "flipkart" in url:
                    st.success("Detected Platform: Flipkart")
                    data = scrape_flipkart(soup)
                elif "meesho" in url:
                    st.success("Detected Platform: Meesho")
                    data = scrape_meesho(soup)
                else:
                    st.error("URL not recognized. Only Amazon, Flipkart, and Meesho supported.")
                    data = None

                # Display Data
                if data:
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        if data.get('image_url'):
                            st.image(data['image_url'], caption="Product Image")
                            
                            # Download Button Logic
                            try:
                                img_response = requests.get(data['image_url'])
                                img_bytes = BytesIO(img_response.content)
                                st.download_button(
                                    label="Download Image",
                                    data=img_bytes,
                                    file_name="product_image.jpg",
                                    mime="image/jpeg"
                                )
                            except:
                                st.write("Error preparing download.")
                        else:
                            st.write("No Image Found")

                    with col2:
                        st.subheader(data.get('title', 'No Title'))
                        
                        st.markdown("### Description")
                        st.write(data.get('description', 'No description'))
                        
                        st.markdown("### Top Review")
                        st.info(data.get('review', 'No review available'))

                        # Generate Keywords
                        st.markdown("### Generated Keywords")
                        keywords = extract_keywords(data.get('title', '') + " " + data.get('description', ''))
                        st.write(", ".join(keywords))
                        
                        # Export Data
                        df = pd.DataFrame([data])
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "Download Data as CSV",
                            csv,
                            "product_data.csv",
                            "text/csv",
                            key='download-csv'
                        )
