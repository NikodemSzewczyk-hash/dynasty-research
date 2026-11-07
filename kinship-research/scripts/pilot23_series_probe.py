#!/usr/bin/env python3
"""Temporary bounded HTML shape probe; no metadata is published."""
from html.parser import HTMLParser
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json

URLS={
"nber":"https://ideas.repec.org/s/nbr/nberwo.html",
"cepr":"https://ideas.repec.org/s/cpr/ceprdp.html",
"iza":"https://ideas.repec.org/s/iza/izadps.html",
"cepr_official":"https://cepr.org/publications/publication-series/discussion-papers",
"iza_official":"https://iza.org/publications/dp"
}
class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.href=None;self.text=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":self.href=dict(attrs).get("href");self.text=[]
    def handle_data(self,data):
        if self.href is not None:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            label=" ".join(" ".join(self.text).split())
            if label:self.links.append((self.href,label))
            self.href=None;self.text=[]
def main():
    for name,url in URLS.items():
        try:
            with urlopen(Request(url,headers={"User-Agent":"dynasty-research/0.4 (academic bibliographic metadata pilot)"}),timeout=30) as r:
                html=r.read(2000000).decode("utf-8",errors="replace")
            p=Links();p.feed(html)
            matches=[(href,label[:140]) for href,label in p.links if any(x in href.lower() for x in ("/p/nbr/nberwo/","/p/cpr/ceprdp/","/p/iza/izadps/","/dp","/discussion"))]
            print(json.dumps({"name":name,"bytes":len(html),"total_links":len(p.links),"matched_links":matches[:8],"html_prefix":html[:100],"first_match_context":html[max(0,html.find(matches[2][0])-260):html.find(matches[2][0])+460] if len(matches)>2 else ""},ensure_ascii=False))
        except Exception as e:print(json.dumps({"name":name,"error":str(e)}))
if __name__=="__main__":main()
