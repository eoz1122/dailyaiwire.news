import requests

urls = [
    "https://images.unsplash.com/photo-1677442136019-21780ecad995",
    "https://images.unsplash.com/photo-1684369175833-31f661066f91",
    "https://images.unsplash.com/photo-1697577418970-95d99b5a55cf",
    "https://images.unsplash.com/photo-1675271591211-126ad94e495d",
    "https://images.unsplash.com/photo-1485827404703-89b55fcc595e",
    "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158",
    "https://images.unsplash.com/photo-1546776310-eef45dd6d63c",
    "https://images.unsplash.com/photo-1531746790731-6c087fecd65a",
    "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab",
    "https://images.unsplash.com/photo-1551434678-e076c223a692",
    "https://images.unsplash.com/photo-1460925895917-afdab827c52f",
    "https://images.unsplash.com/photo-1556155092-490a1ba16284",
    "https://images.unsplash.com/photo-1518770660439-4636190af475",
    "https://images.unsplash.com/photo-1550745679-33d016c823b4",
    "https://images.unsplash.com/photo-1519389950473-47ba0277781c",
    "https://images.unsplash.com/photo-1531297484001-80022131f5a1",
    "https://images.unsplash.com/photo-1450101499163-c8848c66ca85",
    "https://images.unsplash.com/photo-1589829545856-d10d557cf95f",
    "https://images.unsplash.com/photo-1521791136064-7986c308457c",
    "https://images.unsplash.com/photo-1423592707957-3b212afa6733",
    "https://images.unsplash.com/photo-1507413245164-6160d8298b31",
    "https://images.unsplash.com/photo-1532187863486-abf9d39d999a",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa",
    "https://images.unsplash.com/photo-1579154235602-381747ef2232",
    "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
    "https://images.unsplash.com/photo-1563986768609-322da13575f3",
    "https://images.unsplash.com/photo-1614064641938-3bbee52942c7",
    "https://images.unsplash.com/photo-1558494949-ef010955d0ef",
    "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620",
    "https://images.unsplash.com/photo-1491438590914-bc09fcaaf77a",
    "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4",
    "https://images.unsplash.com/photo-1522202176988-66273c2fd55f"
]

for url in urls:
    full_url = f"{url}?auto=format&fit=crop&q=80&w=1200"
    try:
        r = requests.head(full_url)
        if r.status_code != 200:
            print(f"BAD ({r.status_code}): {url}")
        else:
            print(f"OK: {url}")
    except Exception as e:
        print(f"ERROR: {url} - {str(e)}")
