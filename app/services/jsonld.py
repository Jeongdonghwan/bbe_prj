"""구조화 데이터(JSON-LD) 빌더 — 페이지 종류별로 여기서만 만든다 (2026-10-07).

템플릿은 `{% for j in jsonld %}<script type="application/ld+json">{{ j | tojson }}</script>{% endfor %}`.
"""


def organization(origin, name, logo):
    return {"@context": "https://schema.org", "@type": "Organization", "name": name, "url": origin + "/",
            "logo": origin + logo}


def website(origin, name, desc):
    return {"@context": "https://schema.org", "@type": "WebSite", "name": name, "url": origin + "/",
            "description": desc, "inLanguage": "ko"}


def breadcrumb(origin, crumbs, here):
    """crumbs: [(이름, 경로 또는 None)] — None 은 현재 페이지(here)."""
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": origin + (p or here)}
                                for i, (n, p) in enumerate([("홈", "/")] + list(crumbs))]}


def faq(qas):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}}
                           for x in qas]}


def itemlist(origin, items):
    """items: [(이름, 경로)] — 목록 페이지(캐러셀 후보)."""
    return {"@context": "https://schema.org", "@type": "ItemList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "url": origin + p}
                                for i, (n, p) in enumerate(items)]}


def article(origin, post, org_name):
    return {"@context": "https://schema.org", "@type": "Article", "headline": post["title"][:110],
            "description": post["desc"], "datePublished": post["date"].isoformat(),
            "dateModified": max(post["date"], post["updated"]).isoformat(),
            "author": {"@type": "Organization", "name": org_name},
            "publisher": {"@type": "Organization", "name": org_name},
            "mainEntityOfPage": origin + post["path"], "inLanguage": "ko"}


def place_area(region, sido):
    return {"@context": "https://schema.org", "@type": "Place", "name": region,
            "containedInPlace": {"@type": "AdministrativeArea", "name": sido}}


def service(origin, name, desc, path, low_price, org_name):
    return {"@context": "https://schema.org", "@type": "Service", "name": name, "description": desc,
            "provider": {"@type": "Organization", "name": org_name}, "areaServed": "KR", "url": origin + path,
            "offers": {"@type": "AggregateOffer", "priceCurrency": "KRW", "lowPrice": low_price}}
