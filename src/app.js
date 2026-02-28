const CATEGORY_ORDER = ["All", "GenAI", "Azure", "GCP", "AWS", "Industry"];

const state = {
  activeCategory: "All",
  query: "",
  stories: [],
  generatedAt: "",
};

const refs = {
  today: document.getElementById("today"),
  stats: document.getElementById("stats"),
  categoryFilters: document.getElementById("category-filters"),
  searchInput: document.getElementById("search-input"),
  cardGrid: document.getElementById("card-grid"),
  empty: document.getElementById("empty-state"),
  cardTemplate: document.getElementById("news-card-template"),
};

refs.today.textContent = `Updated: ${new Date().toLocaleString(undefined, {
  dateStyle: "full",
  timeStyle: "short",
})}`;

init();

async function init() {
  const payload = await loadStories();
  state.stories = payload.stories;
  state.generatedAt = payload.generatedAt;

  refs.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderCards();
  });

  renderFilters();
  renderCards();
}

async function loadStories() {
  try {
    const response = await fetch("./data/sample-feeds.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Data file not found (${response.status})`);
    }
    const payload = await response.json();
    return {
      stories: payload.stories ?? [],
      generatedAt: payload.generatedAt ?? "",
    };
  } catch (error) {
    console.error("Unable to load feed data:", error);
    return { stories: [], generatedAt: "" };
  }
}

function renderFilters() {
  refs.categoryFilters.innerHTML = "";

  CATEGORY_ORDER.forEach((category) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `chip ${category === state.activeCategory ? "active" : ""}`.trim();
    btn.textContent = category;
    btn.addEventListener("click", () => {
      state.activeCategory = category;
      renderFilters();
      renderCards();
    });
    refs.categoryFilters.appendChild(btn);
  });
}

function renderCards() {
  refs.cardGrid.innerHTML = "";

  const visibleStories = state.stories.filter((story) => {
    const categoryMatch = state.activeCategory === "All" || story.category === state.activeCategory;
    if (!categoryMatch) {
      return false;
    }

    if (!state.query) {
      return true;
    }

    const haystack = `${story.title} ${story.summary} ${story.source}`.toLowerCase();
    return haystack.includes(state.query);
  });

  refs.stats.textContent = `Showing ${visibleStories.length} of ${state.stories.length} stories${state.generatedAt ? ` | Generated: ${formatDateTime(state.generatedAt)}` : ""}`;

  if (visibleStories.length === 0) {
    refs.empty.classList.remove("hidden");
    return;
  }
  refs.empty.classList.add("hidden");

  visibleStories.forEach((story) => {
    const card = refs.cardTemplate.content.firstElementChild.cloneNode(true);
    card.querySelector(".tag").textContent = story.category;
    card.querySelector(".source").textContent = `${story.source} | ${formatDate(story.publishedAt)}`;
    card.querySelector(".title").textContent = story.title;
    card.querySelector(".summary").textContent = story.summary;
    card.querySelector(".details").textContent = story.details;

    const link = card.querySelector(".read-link");
    link.href = story.url;

    refs.cardGrid.appendChild(card);
  });
}

function formatDate(isoDate) {
  if (!isoDate) {
    return "Date unavailable";
  }
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatDateTime(isoDate) {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
