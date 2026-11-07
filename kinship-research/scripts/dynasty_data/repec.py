"""Bounded RePEc public series-listing metadata adapter.

Uses only the three verified IDEAS/RePEc series pages. This is a recent
listing, not the RePEc API, a PDF downloader, or a full historical archive.
"""
from __future__ import annotations
from html import unescape
from html.parser import HTMLParser
import re
from urllib.request import Request, urlopen
from urllib.parse import urljoin

HANDLES={
    "RePEc:nbr:nberwo":("nbr","nberwo"),
    "RePEc:cpr:ceprdp":("cpr","ceprdp"),
    "RePEc:iza:izadps":("iza","izadps"),
}
BASE="https://ideas.repec.org"

def listing_url(handle: str) -> str:
    if handle not in HANDLES:
        raise ValueError("Unverified RePEc series handle")
    archive,series=HANDLES[handle]
    return f"{BASE}/s/{archive}/{series}.html"

class _Parser(HTMLParser):
    def __init__(self,handle):
        super().__init__(convert_charrefs=True)
        self.handle=handle
        self.archive,self.series=HANDLES[handle]
        self.year=None
        self.header=None
        self.in_li=False
        self.in_anchor=False
        self.anchor_href=None
        self.anchor_text=[]
        self.li_text=[]
        self.li_title=None
        self.li_href=None
        self.li_after_title=[]
        self.records=[]
        self.seen=set()

    def handle_starttag(self,tag,attrs):
        attr=dict(attrs)
        if tag in ("h2","h3"): self.header=tag
        if tag=="li" and "list-group-item" in attr.get("class",""):
            self._flush()
            self.in_li=True
            self.li_title=None;self.li_href=None;self.li_text=[];self.li_after_title=[]
        if tag=="a" and self.in_li:
            self.in_anchor=True
            self.anchor_href=attr.get("href","")
            self.anchor_text=[]

    def handle_data(self,data):
        text=unescape(data)
        if self.header=="h3":
            m=re.fullmatch(r"\s*((?:19|20)\d{2})\s*",text)
            if m:self.year=int(m.group(1))
        if self.in_li:
            self.li_text.append(text)
            if self.in_anchor:self.anchor_text.append(text)
            elif self.li_href:self.li_after_title.append(text)

    def handle_endtag(self,tag):
        if tag in ("h2","h3"):self.header=None
        if tag=="a" and self.in_anchor:
            self.in_anchor=False
            href=self.anchor_href or ""
            prefix=f"/p/{self.archive}/{self.series}/"
            if href.startswith(prefix) and re.fullmatch(r"[A-Za-z0-9_-]+\.html",href[len(prefix):]):
                title=" ".join(" ".join(self.anchor_text).split())
                if title and title.casefold() not in ("by citations","by downloads"):
                    self.li_title=title
                    self.li_href=href
        if tag=="li":self._flush()

    def _flush(self):
        if self.in_li and self.li_title and self.li_href:
            suffix=self.li_href.rsplit("/",1)[-1].removesuffix(".html")
            pid=f"{self.handle}:{suffix}"
            if pid not in self.seen:
                self.seen.add(pid)
                tail=" ".join(" ".join(self.li_after_title).split())
                # The listing presents "by" then authors separated by ampersands.
                if tail.casefold().startswith("by "):tail=tail[3:]
                authors=[a.strip() for a in tail.split(" & ") if a.strip() and a.strip()!=","]
                self.records.append({
                    "provider":"repec","provider_id":pid,"doi":None,
                    "title":self.li_title,"authors":authors[:30],
                    "year":self.year,"date":None,"source_name":"",
                    "url":urljoin(BASE,self.li_href),"kind":"working_paper",
                    "repec_series_handle":self.handle})
        self.in_li=False

    def close(self):
        super().close()
        self._flush()

def parse_listing(html: str,handle: str,source_name: str,max_records: int=100) -> list[dict]:
    if handle not in HANDLES:raise ValueError("Unverified RePEc handle")
    if not 1<=max_records<=500:raise ValueError("Bounded RePEc cap must be 1..500")
    parser=_Parser(handle)
    parser.feed(html)
    parser.close()
    if not parser.records:
        raise ValueError("RePEc listing layout changed or no matching records; refusing empty success")
    for r in parser.records:
        r["source_name"]=source_name
    return parser.records[:max_records]

def iter_repec(handle: str,source_name: str,max_records: int=100,fetcher=None):
    url=listing_url(handle)
    if fetcher is None:
        req=Request(url,headers={"User-Agent":"dynasty-research/0.4 (+https://dynastyecon.netlify.app/; bounded academic metadata collection)","Accept":"text/html"})
        with urlopen(req,timeout=35) as response:
            body=response.read(2_000_001)
            if len(body)>2_000_000:raise ValueError("RePEc listing exceeds safe 2 MB bound")
            # IDEAS uses UTF-8 pages; replace malformed provider bytes rather than failing.
            html=body.decode("utf-8",errors="replace")
    else:
        html=fetcher(url)
    yield from parse_listing(html,handle,source_name,max_records)
