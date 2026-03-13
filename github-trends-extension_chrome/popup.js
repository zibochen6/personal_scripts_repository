document.addEventListener('DOMContentLoaded', () => {
    const btnAi = document.getElementById('btn-ai');
    const btnJetson = document.getElementById('btn-jetson');
    const contentList = document.getElementById('content-list');

    let currentType = 'ai';
    let currentPage = 1;
    let isLoading = false;
    let hasMore = true;

    // Load AI trends by default
    resetAndFetch('ai');

    btnAi.addEventListener('click', () => {
        if (currentType !== 'ai') {
            setActiveTab(btnAi, btnJetson);
            resetAndFetch('ai');
        }
    });

    btnJetson.addEventListener('click', () => {
        if (currentType !== 'jetson') {
            setActiveTab(btnJetson, btnAi);
            resetAndFetch('jetson');
        }
    });

    contentList.addEventListener('scroll', () => {
        if (isLoading || !hasMore) return;
        
        const { scrollTop, scrollHeight, clientHeight } = contentList;
        // If scrolled to bottom (with 50px threshold)
        if (scrollTop + clientHeight >= scrollHeight - 50) {
            currentPage++;
            fetchData(currentType, currentPage);
        }
    });

    function setActiveTab(active, inactive) {
        active.classList.add('active');
        inactive.classList.remove('active');
    }

    function resetAndFetch(type) {
        currentType = type;
        currentPage = 1;
        hasMore = true;
        contentList.innerHTML = ''; // Clear previous content
        fetchData(type, currentPage);
    }

    async function fetchData(type, page) {
        if (isLoading) return;
        isLoading = true;
        
        // Show loading indicator at the bottom if it's not the first page
        let loadingIndicator = null;
        if (page === 1) {
            contentList.innerHTML = '<div class="loading">Loading...</div>';
        } else {
            loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'loading';
            loadingIndicator.textContent = 'Loading more...';
            contentList.appendChild(loadingIndicator);
        }

        try {
            let query = '';
            let sort = '';
            
            if (type === 'ai') {
                // Hot AI projects: "Hot" means high stars and active recently
                // We search for repositories with topic "ai", created in the last 6 months, sorted by stars.
                // Using spaces instead of '+' to ensure correct URL encoding by encodeURIComponent
                const date = new Date();
                date.setMonth(date.getMonth() - 6);
                const dateString = date.toISOString().split('T')[0];
                query = `topic:ai created:>${dateString}`;
                sort = 'stars';
            } else {
                // Latest Jetson projects: keyword "jetson", filtered by stars >= 10, sorted by updated time
                query = 'jetson stars:>=10';
                sort = 'updated';
            }

            const url = `https://api.github.com/search/repositories?q=${encodeURIComponent(query)}&sort=${sort}&order=desc&per_page=10&page=${page}`;
            
            const response = await fetch(url);
            if (!response.ok) {
                if (response.status === 403) {
                    throw new Error('API Rate limit exceeded. Please try again later.');
                }
                throw new Error('Network response was not ok');
            }
            
            const data = await response.json();
            
            // Remove loading indicator(s)
            if (page === 1) {
                contentList.innerHTML = '';
            } else if (loadingIndicator) {
                loadingIndicator.remove();
            }

            if (data.items && data.items.length > 0) {
                renderList(data.items);
            } else {
                hasMore = false;
                if (page === 1) {
                    contentList.innerHTML = '<div class="loading">No repositories found.</div>';
                } else {
                    const endMsg = document.createElement('div');
                    endMsg.className = 'loading';
                    endMsg.textContent = 'No more results.';
                    contentList.appendChild(endMsg);
                }
            }
        } catch (error) {
            if (page === 1) {
                contentList.innerHTML = `<div class="error">Error: ${error.message}</div>`;
            } else if (loadingIndicator) {
                loadingIndicator.textContent = 'Error loading more items.';
            }
        } finally {
            isLoading = false;
        }
    }

    function renderList(items) {
        const fragment = document.createDocumentFragment();
        
        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'repo-item';
            div.innerHTML = `
                <a href="${item.html_url}" target="_blank" class="repo-name">${item.full_name}</a>
                <div class="repo-desc">${item.description || 'No description available'}</div>
                <div class="repo-meta">
                    <span class="stars">⭐ ${formatNumber(item.stargazers_count)}</span>
                    <span class="lang">${item.language || 'Unknown'}</span>
                    <span class="updated">Updated: ${new Date(item.updated_at).toLocaleDateString()}</span>
                </div>
            `;
            fragment.appendChild(div);
        });
        
        contentList.appendChild(fragment);
    }

    function formatNumber(num) {
        if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'k';
        }
        return num;
    }
});
