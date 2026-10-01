import os
import re
from ..models import MatchData
class GenericCollector:
    def __init__(self,name):self.name=name
    async def fetch(self,day,cfg):
        from playwright.async_api import async_playwright
        out=[]
        async with async_playwright() as p:
            browser_path=os.environ.get("BETPROFESSIONAL_CHROMIUM")
            launch_args={"headless":cfg.get("headless",True)}
            if browser_path:
                launch_args["executable_path"]=browser_path
            browser=await p.chromium.launch(**launch_args)
            page=await browser.new_page()
            try:
                await page.goto(cfg["url"],wait_until="domcontentloaded",timeout=90000)
                await page.wait_for_timeout(4000)
                rows=page.locator("table tbody tr")
                for i in range(min(await rows.count(),1000)):
                    txt=(await rows.nth(i).inner_text()).strip()
                    m=re.search(r"\s+[-–—]\s+",txt)
                    if m:
                        a=txt[:m.start()].strip().splitlines()[-1];b=txt[m.end():].strip().splitlines()[0]
                        if a and b:out.append(MatchData(a,b,day,source=self.name,raw_text=txt[:2000]))
            finally: await browser.close()
        return out
