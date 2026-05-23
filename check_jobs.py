import re
import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

# ── CONFIG ──────────────────────────────────────────────────────────────────
URL = "https://www.findababysitter.com.au/browse/jobs/vic/clarinda"
SEEN_JOBS_FILE = "seen_jobs.json"
MAX_DISTANCE_KM = 15          # Set to None to disable distance filter

EMAIL_SENDER   = os.environ.get("EMAIL_SENDER")    # set in GitHub Secrets
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")  # Gmail App Password
EMAIL_TO       = os.environ.get("EMAIL_TO")
# ────────────────────────────────────────────────────────────────────────────

def load_seen():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE) as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen, f, indent=2)

def fetch_jobs():
    headers = {"User-Agent": "Mozilla/5.0"}
    jobs = []
    page = 1

    while True:
        paged_url = URL if page == 1 else f"{URL}?page={page}"
        resp = requests.get(paged_url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("div", class_="carer-new-block-main")

        if not cards:
            break  # no more pages

        all_beyond_range = True  # track if every card on this page is too far

        for card in cards:
            # Title + link
            link_tag = card.find("a", href=True)
            title_tag = card.find("h5", class_="carer-new-block__name")
            title = re.sub(r'^NEW!', '', title_tag.get_text(strip=True)) if title_tag else "Unknown"
            link = link_tag["href"] if link_tag else ""
            if link and not link.startswith("http"):
                link = "https://www.findababysitter.com.au" + link
            job_id = link.rstrip("/").split("/")[-1]

            # Suburb + distance (e.g. "Bentleigh East, VIC | 5 km")
            suburb_tag = card.find("p", class_="carer-new-block__suburb-age")
            suburb_text = suburb_tag.get_text(strip=True) if suburb_tag else ""

            # Extract distance in km from the text
            dist_match = re.search(r'\|\s*([\d.]+)\s*km', suburb_text)
            distance_km = float(dist_match.group(1)) if dist_match else None

            # Clean suburb name (strip the "| X km" part)
            suburb = re.sub(r'\|.*', '', suburb_text).strip()

            # Posted info
            posted_tag = card.find("p", class_="job-info-block__post")
            posted = " ".join(posted_tag.get_text(separator=" ", strip=True).split()) if posted_tag else ""

            # About section
            about_div = card.find("div", class_="carer-new-block-about")
            if about_div:
                about_p = about_div.find("p")
                about = about_p.get_text(separator=" ", strip=True) if about_p else ""
            else:
                about = ""

            if distance_km is None or distance_km <= MAX_DISTANCE_KM:
                all_beyond_range = False

            jobs.append({
                "id":          job_id,
                "title":       title,
                "link":        link,
                "suburb":      suburb,
                "distance_km": distance_km,
                "posted":      posted,
                "about":       about,
            })

        # Since results are sorted by distance, once an entire page is beyond
        # the limit we know all subsequent pages will be too — stop early
        if MAX_DISTANCE_KM is not None and all_beyond_range:
            break

        page += 1

    return jobs

def within_range(job):
    if MAX_DISTANCE_KM is None:
        return True
    if job["distance_km"] is not None:
        return job["distance_km"] <= MAX_DISTANCE_KM
    return True  # include if distance unknown

def send_email(new_jobs):
    body = "New babysitting jobs near Clarinda:\n\n"
    for j in new_jobs:
        dist = f" (~{j['distance_km']:.0f} km away)" if j["distance_km"] is not None else ""
        about_line = f"  {j['about']}\n" if j.get("about") else ""
        body += (
            f"• {j['title']}{dist}\n"
            f"  {j['suburb']}\n"
            f"  {j['posted']}\n"
            f"{about_line}"
            f"  {j['link']}\n\n"
        )

    msg = MIMEText(body)
    msg["Subject"] = f"🍼 {len(new_jobs)} new babysitting job(s) near Clarinda"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

def main():
    seen = load_seen()
    jobs = fetch_jobs()
    new_jobs = []

    for job in jobs:
        if job["id"] not in seen and within_range(job):
            new_jobs.append(job)
            seen[job["id"]] = job["title"]

    if new_jobs:
        send_email(new_jobs)

    save_seen(seen)
    print(f"Done. {len(new_jobs)} new job(s) found.")

if __name__ == "__main__":
    main()
