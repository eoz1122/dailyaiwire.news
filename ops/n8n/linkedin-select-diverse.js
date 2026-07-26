const TIME_ZONE = 'America/New_York';
const DAILY_LIMIT = 24;
const DAILY_RESEARCH_LIMIT = 6;
const DAILY_SOURCE_LIMIT = 4;
const DAILY_CATEGORY_LIMIT = 6;
const MAX_PROCESSED_IDS = 500;

function localClock(now) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now).reduce((result, part) => {
    result[part.type] = part.value;
    return result;
  }, {});

  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

function diversityMetadata(item) {
  const rawCategories = Array.isArray(item.json.categories)
    ? item.json.categories
    : [item.json.category].filter(Boolean);
  const categories = rawCategories.map(value => String(value || '').trim()).filter(Boolean);
  const sourceToken = categories.find(value => value.toLowerCase().startsWith('source:'));
  const researchToken = categories.find(value => value.toLowerCase().startsWith('research:'));
  const category = categories.find(value => {
    const normalized = value.toLowerCase();
    return !normalized.startsWith('source:') && !normalized.startsWith('research:');
  }) || 'AI News';
  const source = sourceToken ? sourceToken.slice('source:'.length).trim() : 'Unknown';
  const isResearch = researchToken
    ? researchToken.slice('research:'.length).trim() === '1'
    : false;

  return {
    category,
    categoryKey: category.toLowerCase(),
    source,
    sourceKey: source.toLowerCase(),
    isResearch,
  };
}

function resetDailyState(staticData, date) {
  staticData.dailyDate = date;
  staticData.dailySuccessfulPosts = 0;
  staticData.dailyResearchPosts = 0;
  staticData.dailySourceCounts = {};
  staticData.dailyCategoryCounts = {};
}

const now = new Date();
const clock = localClock(now);
const staticData = $getWorkflowStaticData('global');
const items = $input.all().filter(item => item?.json?.link);

if (staticData.dailyDate !== clock.date) {
  resetDailyState(staticData, clock.date);
}
staticData.dailyResearchPosts = Number(staticData.dailyResearchPosts || 0);
staticData.dailySourceCounts = staticData.dailySourceCounts || {};
staticData.dailyCategoryCounts = staticData.dailyCategoryCounts || {};

if (!staticData.initializedAt) {
  staticData.processedIds = [...new Set(items.map(item => item.json.link))].slice(-MAX_PROCESSED_IDS);
  staticData.initializedAt = now.toISOString();
  resetDailyState(staticData, clock.date);
  return [];
}

if (clock.minutes < 6 * 60) {
  return [];
}

if (Number(staticData.dailySuccessfulPosts || 0) >= DAILY_LIMIT) {
  return [];
}

const processedIds = new Set(staticData.processedIds || []);
const candidates = items
  .map(item => {
    const dateValue = item.json.isoDate || item.json.pubDate || item.json.pubdate || '';
    const timestamp = Date.parse(dateValue);
    return {
      item,
      articleId: item.json.link,
      timestamp: Number.isFinite(timestamp) ? timestamp : 0,
      ...diversityMetadata(item),
    };
  })
  .filter(candidate => !processedIds.has(candidate.articleId))
  .filter(candidate => (
    Number(staticData.dailySourceCounts[candidate.sourceKey] || 0) < DAILY_SOURCE_LIMIT
    && Number(staticData.dailyCategoryCounts[candidate.categoryKey] || 0) < DAILY_CATEGORY_LIMIT
    && (!candidate.isResearch || staticData.dailyResearchPosts < DAILY_RESEARCH_LIMIT)
  ))
  .sort((left, right) => right.timestamp - left.timestamp);

if (!candidates.length) {
  return [];
}

const selected = candidates[0];
const output = {
  json: {
    ...selected.item.json,
    articleId: selected.articleId,
    selectionSource: selected.source,
    selectionSourceKey: selected.sourceKey,
    selectionCategory: selected.category,
    selectionCategoryKey: selected.categoryKey,
    selectionIsResearch: selected.isResearch,
  },
};
if (selected.item.binary) {
  output.binary = selected.item.binary;
}
return [output];
