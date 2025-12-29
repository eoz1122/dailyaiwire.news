# 📸 Fallback Image Guide for DailyAIWire.news

## ✅ Issues Fixed

1. **Removed Unsplash query parameters** from local image paths
2. **Converted full URLs to relative paths** in database (223 articles updated)
3. **Updated fetcher.py and randomize script** to use clean paths

---

## 📐 Image Specifications

### **Recommended Specs:**

- **Dimensions**: 1200px × 800px (3:2 aspect ratio) ← **BEST CHOICE**
- **Format**: JPEG (.jpg)
- **File Size**: 80-400 KB
- **Quality**: 80-85% JPEG compression

### **Alternative Dimensions:**

- 1200px × 675px (16:9 widescreen)
- 1920px × 1280px (3:2 high quality)
- 1600px × 900px (16:9 high quality)

---

## 🎨 Adding Your Own Images

### **Step 1: Prepare Your Images**

Make sure your images are:

- **1200×800 pixels** (or one of the alternative sizes above)
- **Saved as JPEG** with 80-85% quality
- **Under 400 KB** in file size
- **Landscape orientation** (wider than tall)

### **Step 2: Name Your Files**

Use this naming convention:

```
[category]_[number].jpg
```

**Available categories:**

- `business` - Corporate AI, funding, M&A
- `llms` - Language models, GPT, Claude, etc.
- `robotics` - Physical AI, robots, automation
- `tools` - AI applications, software
- `policy` - Regulation, government, ethics
- `science` - Research, breakthroughs, papers
- `security` - Cybersecurity, AI safety
- `society` - Social impact, culture

**Examples:**

- `business_2.jpg` (third business image)
- `llms_2.jpg` (third LLM image)
- `robotics_2.jpg` (third robotics image)

### **Step 3: Add Files to Directory**

Place your images in:

```
static/fallbacks/
```

### **Step 4: Update the Code**

If you're adding a third image (_2.jpg) to each category, update these files:

**File: `fetcher.py` (around line 500)**
Add `"/static/fallbacks/[category]_2.jpg"` to each category list.

**File: `scripts/randomize_existing_images.py` (around line 6)**
Add `"/static/fallbacks/[category]_2.jpg"` to each category list.

---

## 🔄 How to Randomize Existing Articles

After adding new images, run this script to update existing articles:

```bash
python scripts/randomize_existing_images.py
```

This will randomly assign one of the available fallback images to each article in that category.

---

## 🧪 Testing

### **Test Locally:**

1. Start the Flask app: `python app.py`
2. Visit: `http://localhost:8000/rss.xml`
3. Check that all `<enclosure>` tags have valid image URLs

### **Test on VPS:**

1. Push changes to git
2. Pull on VPS
3. Restart the app
4. Visit: `https://dailyaiwire.news/rss.xml`
5. Validate RSS feed: <https://validator.w3.org/feed/>

---

## 📊 Current Image Distribution

As of last check, here's how your fallback images are distributed:

| Category  | Variants | Total |
|-----------|----------|-------|
| Business  | 0, 1, 2, 3 | 97    |
| LLMs      | 0, 1, 2  | 34    |
| Tools     | 0, 1, 2  | 37    |
| Science   | 0, 1, 2  | 18    |
| Policy    | 0, 1, 2, 3 | 11    |
| Robotics  | 0, 1, 2  | 9     |
| Security  | 0, 1, 2, 3 | 8     |
| Society   | 0, 1, 2, 3, 4 | 9     |

**Total**: 223 articles using fallback images

---

## 🎯 Quick Reference

**Current working images:**

```
/static/fallbacks/business_0.jpg    ✅
/static/fallbacks/business_1.jpg    ✅
/static/fallbacks/business_2.jpg    ✅
/static/fallbacks/business_3.jpg    ✅ (New)
/static/fallbacks/llms_0.jpg        ✅
/static/fallbacks/llms_1.jpg        ✅
/static/fallbacks/llms_2.jpg        ✅
/static/fallbacks/policy_0.jpg      ✅
/static/fallbacks/policy_1.jpg      ✅
/static/fallbacks/policy_2.jpg      ✅
/static/fallbacks/policy_3.jpg      ✅ (New)
/static/fallbacks/robotics_0.jpg    ✅
/static/fallbacks/robotics_1.jpg    ✅
/static/fallbacks/robotics_2.jpg    ✅
/static/fallbacks/science_0.jpg     ✅
/static/fallbacks/science_1.jpg     ✅
/static/fallbacks/science_2.jpg     ✅
/static/fallbacks/security_0.jpg    ✅
/static/fallbacks/security_1.jpg    ✅
/static/fallbacks/security_2.jpg    ✅
/static/fallbacks/security_3.jpg    ✅ (New)
/static/fallbacks/society_0.jpg     ✅
/static/fallbacks/society_1.jpg     ✅
/static/fallbacks/society_2.jpg     ✅
/static/fallbacks/society_3.jpg     ✅ (New)
/static/fallbacks/society_4.jpg     ✅ (New)
/static/fallbacks/tools_0.jpg       ✅
/static/fallbacks/tools_1.jpg       ✅
/static/fallbacks/tools_2.jpg       ✅
```

---

## 🚀 Next Steps

1. **Create or source 8 new images** (one for each category)
2. **Resize them to 1200×800** pixels
3. **Save as JPEG** with 80-85% quality
4. **Name them** using the `[category]_2.jpg` convention
5. **Place in** `static/fallbacks/` directory
6. **Update code** in `fetcher.py` and `randomize_existing_images.py`
7. **Run randomization script** to update existing articles
8. **Test RSS feed** to confirm images load correctly
