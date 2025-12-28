import requests

urls = [
    "https://images.unsplash.com/photo-1677442136019-21780ecad995",
    "https://images.unsplash.com/photo-1620712943543-bcc462824100",
    "https://images.unsplash.com/photo-1555255707-c07966488b7b",
    "https://images.unsplash.com/photo-1676299081847-824916ff030a",
    "https://images.unsplash.com/photo-1485827404703-89b55fcc595e",
    "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158",
    "https://images.unsplash.com/photo-1531746790731-6c087fecd05a",
    "https://images.unsplash.com/photo-1516110833967-0b5716ca1387",
    "https://images.unsplash.com/photo-1507679799987-c73779587ccf",
    "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab",
    "https://images.unsplash.com/photo-1497366216548-37526070297c",
    "https://images.unsplash.com/photo-1664575602276-acd073f104c1",
    "https://images.unsplash.com/photo-1518770660439-4636190af475",
    "https://images.unsplash.com/photo-1550009158-9ebf69173e03",
    "https://images.unsplash.com/photo-1519389950473-47ba0277781c",
    "https://images.unsplash.com/photo-1517077304055-6e89abbf09b0",
    "https://images.unsplash.com/photo-1450101499163-c8848c66ca85",
    "https://images.unsplash.com/photo-1589829545856-d10d557cf95f",
    "https://images.unsplash.com/photo-1423592707957-3b212afa6733",
    "https://images.unsplash.com/photo-1505664194779-8beaceb93744",
    "https://images.unsplash.com/photo-1532187863486-abf2ad613a00",
    "https://images.unsplash.com/photo-1579154235602-381747ef2232",
    "https://images.unsplash.com/photo-1507413245164-6160d8298b31",
    "https://images.unsplash.com/photo-1530210124550-912dc1381cb8",
    "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
    "https://images.unsplash.com/photo-1563986768609-322da13575f3",
    "https://images.unsplash.com/photo-1614064641938-3bbee52942c7",
    "https://images.unsplash.com/photo-1510511459019-5dee19ada7dd",
    "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620",
    "https://images.unsplash.com/photo-1491438590914-bc09fcaaf77a",
    "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4",
    "https://images.unsplash.com/photo-1521737604893-d14cc237f11d"
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
