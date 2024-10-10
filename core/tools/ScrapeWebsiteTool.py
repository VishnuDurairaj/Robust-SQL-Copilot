import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field
from typing import List
from bs4 import BeautifulSoup, Comment

from vectorestores import ChromaStore
from semantic_text_splitter import TextSplitter

print("Creating Vector Store......:")

os.environ['ALLOW_RESET']='TRUE'

db = ChromaStore("sample")

splitter = TextSplitter.from_tiktoken_model("gpt-4o", 500)

class ScrapeWebsite(BaseModel):
    """
    Use this tool to scrape data from websites using Playwright.
    """
    search_query: str = Field(
        ..., description="The search query to be entered into Google."
    )

    def run(self) -> List[str]:
        response = db.reset()
        print("Reset : ",response)
        with sync_playwright() as p:

            def get_page_content(href):
                print("Navigating to:", href)
                page.goto(href, wait_until="load", timeout=60000)
                content = page.content()
                return content

            def parse_element(element):
                """
                Recursively parse HTML elements and return formatted text content.
                """
                _content = ""

                if element.name == 'h1':
                    _content = f"# {element.get_text(strip=True)}\n\n"

                elif element.name == 'h2':
                    _content = f"## {element.get_text(strip=True)}\n\n"

                elif element.name == 'h3':
                    _content = f"### {element.get_text(strip=True)}\n\n"

                elif element.name == 'h4':
                    _content = f"#### {element.get_text(strip=True)}\n\n"

                elif element.name == 'h5':
                    _content = f"##### {element.get_text(strip=True)}\n\n"

                elif element.name == 'h6':
                    _content = f"###### {element.get_text(strip=True)}\n\n"

                elif element.name == 'p':
                    _content = f"{element.get_text(strip=True)}\n\n"

                elif element.name == 'ul':
                    for li in element.find_all('li'):
                        _content += f"- {li.get_text(strip=True)}\n"
                    _content += "\n"

                elif element.name == 'ol':
                    for idx, li in enumerate(element.find_all('li'), 1):
                        _content += f"{idx}. {li.get_text(strip=True)}\n"
                    _content += "\n"

                elif element.name == 'table':
                    _content += "| " + " | ".join([th.get_text(strip=True) for th in element.find_all('th')]) + " |\n"
                    _content += "| " + " | ".join(["---" for _ in element.find_all('th')]) + " |\n"
                    for row in element.find_all('tr'):
                        cells = row.find_all(['td', 'th'])
                        _content += "| " + " | ".join(cell.get_text(strip=True) for cell in cells) + " |\n"
                    _content += "\n"

                elif element.name == 'blockquote':
                    _content = f"> {element.get_text(strip=True)}\n\n"

                elif element.name == 'pre':
                    _content = f"```\n{element.get_text(strip=True)}\n```\n\n"

                elif element.name == 'code':
                    _content = f"`{element.get_text(strip=True)}`\n\n"

                # elif element.name == 'a':
                #     href = element.get('href', '#')
                #     link_text = element.get_text(strip=True)
                #     _content = f"[{link_text}]({href})\n\n"

                # elif element.name == 'img':
                #     alt_text = element.get('alt', '')
                #     src = element.get('src', '')
                #     _content = f"![{alt_text}]({src})\n\n"

                elif element.name == 'strong':
                    _content = f"**{element.get_text(strip=True)}**\n\n"

                elif element.name == 'em':
                    _content = f"*{element.get_text(strip=True)}*\n\n"

                elif element.name == 'hr':
                    _content = "---\n\n"

                elif element.name == 'dl':
                    for dt in element.find_all('dt'):
                        _content += f"**{dt.get_text(strip=True)}**\n"
                        for dd in dt.find_next_siblings('dd'):
                            _content += f": {dd.get_text(strip=True)}\n"
                    _content += "\n"

                elif element.name == 'textarea':
                    name = element.get('name', '')
                    _content = f"**Textarea**: `{name}` with value `{element.get_text(strip=True)}`\n\n"

                elif element.name == 'select':
                    name = element.get('name', '')
                    options = [opt.get_text(strip=True) for opt in element.find_all('option')]
                    _content = f"**Select**: `{name}` with options {options}\n\n"

                elif isinstance(element, Comment):
                    _content = ""  # Skip HTML comments

                elif element.name in ['div', 'span', 'article', 'section']:
                    # Recursively process child elements
                    for child in element.children:
                        _content += parse_element(child)

                elif not element.name:

                    _content += element.get_text(strip=True)
                    _content += "\n"

                # else:
                #     with open(f"output.txt", "a", encoding="utf-8") as f:
                #         f.write(f"Tag: {element.name}\n")
                #         f.write(f"{element.get_text(strip=True)}\n")
                #         f.write("-----------------------------\n")

                return _content

            def parse_page_content(page_content, href):
                try:
                    # Use BeautifulSoup to parse the HTML and extract text
                    soup = BeautifulSoup(page_content, "html.parser")

                    # Extract title
                    title = soup.title.string if soup.title else 'No Title'

                    # Start Markdown content with title
                    markdown_content = f"# {title}\n\n"

                    for element in soup.find_all(True):

                        _content = parse_element(element)

                        if _content and _content not in added_content:
                            markdown_content += _content
                            added_content.add(_content)

                    scraped_data.append((href, markdown_content))

                except Exception as e:
                    print(f"Error: {e}")

            scraped_data = []
            added_content = set()
            browser = p.chromium.launch(headless=True)  # Switch to headed mode for debugging
            page = browser.new_page()

            # Navigate to Google
            page.goto("https://www.google.com", wait_until="networkidle")  # Wait until network is idle
            page.wait_for_selector("#APjFqb", timeout=60000)  # Explicit wait

            # Fill the search input and submit the query
            page.fill("#APjFqb", self.search_query)
            page.press("#APjFqb", "Enter")

            # Wait for the results to load
            page.wait_for_selector('h3', timeout=60000)

            # Extract Content from Google search results page
            page_content = page.content()
            parse_page_content(page_content, "Google Search Result")

            # Evaluate JavaScript to get all the hrefs
            links = page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a h3')).map(el => el.closest('a').href);
            }''')

            print("Links Found:", links)

            for href in links[:3]:
                try:
                    page_content = get_page_content(href)
                    parse_page_content(page_content, href)
                except Exception as e:
                    print(e)

            browser.close()

        if len(scraped_data):

            contents = [i[1] for i in scraped_data]
            source = [{"source": i[0]} for i in scraped_data]

            print("Splitting the text......", source)

            all_chunks = []
            all_sources = []

            for i, j in zip(contents, source):
                chunks = splitter.chunks(i)
                sor = [j] * len(chunks)
                all_chunks.extend(chunks)
                all_sources.extend(sor)

            db.add_documents(all_chunks, [str(i) for i in range(len(all_chunks))], meta_data=all_sources)
            
            top_n = 5

            if len(all_chunks) <= top_n:
                print(f"There are {len(all_chunks)} chunks available...")
                top_n = len(all_chunks)

            relevant_documents = db.get_relavant_documents(self.search_query, top_n)
            sources = [i['source'] for i in relevant_documents['metadatas'][0]]
            documents = [f"Source : {j}\n{i}\n\n" for i, j in zip(relevant_documents['documents'][0], sources)]

            return "\n".join(documents)
        else:
            return "Sorry, I could not find the details"


# if __name__ == "__main__":
#     scraper = ScrapeWebsite(search_query="Who is the CEO of factspan")
#     scraped_content = scraper.run()

#     print(len(scraped_content))

#     # for i, content in enumerate(scraped_content, 1):
#     #     with open(f"mds/{i}.md", "w", encoding="utf-8") as f:
#     #         if content[1]:
#     #             f.write(f"Source : {content[0]}\n\n")
#     #             f.write(content[1])


from fastapi import FastAPI
import uvicorn, requests
from pydantic import BaseModel

class SearchQuery(BaseModel):
    search_quer : str

app = FastAPI()

@app.post("/search_online")
def search_online(args:SearchQuery):

    try:

        scraper = ScrapeWebsite(search_query=args.search_quer)
        scraped_content = scraper.run()

        return scraped_content
    
    except Exception as e:

        return f"I could not find the details.: {e}"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8088)
