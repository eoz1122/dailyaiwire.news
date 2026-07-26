const TIME_ZONE = 'America/New_York';
const DAILY_LIMIT = 24;
const MAX_PROCESSED_IDS = 500;

function localDate(now) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now).reduce((result, part) => {
    result[part.type] = part.value;
    return result;
  }, {});
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function resetDailyState(staticData, date) {
  staticData.dailyDate = date;
  staticData.dailySuccessfulPosts = 0;
  staticData.dailyResearchPosts = 0;
  staticData.dailySourceCounts = {};
  staticData.dailyCategoryCounts = {};
}

const selected = $('Select Next Article').first();
const articleId = selected?.json?.articleId || selected?.json?.link;
if (!articleId) {
  throw new Error('Successful LinkedIn response is missing the selected article ID');
}

const now = new Date();
const date = localDate(now);
const staticData = $getWorkflowStaticData('global');

if (staticData.dailyDate !== date) {
  resetDailyState(staticData, date);
}

staticData.processedIds = staticData.processedIds || [];
const alreadyProcessed = staticData.processedIds.includes(articleId);
const sourceKey = String(selected.json.selectionSourceKey || 'unknown').toLowerCase();
const categoryKey = String(selected.json.selectionCategoryKey || 'ai news').toLowerCase();
staticData.dailySourceCounts = staticData.dailySourceCounts || {};
staticData.dailyCategoryCounts = staticData.dailyCategoryCounts || {};

if (!alreadyProcessed) {
  staticData.processedIds.push(articleId);
  staticData.processedIds = staticData.processedIds.slice(-MAX_PROCESSED_IDS);
  staticData.dailySuccessfulPosts = Math.min(
    DAILY_LIMIT,
    Number(staticData.dailySuccessfulPosts || 0) + 1,
  );
  staticData.dailySourceCounts[sourceKey] = Number(staticData.dailySourceCounts[sourceKey] || 0) + 1;
  staticData.dailyCategoryCounts[categoryKey] = Number(staticData.dailyCategoryCounts[categoryKey] || 0) + 1;
  staticData.dailyResearchPosts = Number(staticData.dailyResearchPosts || 0)
    + (selected.json.selectionIsResearch ? 1 : 0);
}

return $input.all().map(item => {
  const output = {
    json: {
      ...item.json,
      articleId,
      postedAt: now.toISOString(),
      dailySuccessfulPosts: staticData.dailySuccessfulPosts,
      dailyResearchPosts: staticData.dailyResearchPosts,
      dailySourcePosts: Number(staticData.dailySourceCounts[sourceKey] || 0),
      dailyCategoryPosts: Number(staticData.dailyCategoryCounts[categoryKey] || 0),
    },
  };
  if (item.binary) {
    output.binary = item.binary;
  }
  return output;
});
