document.addEventListener('DOMContentLoaded', () => {
    // Sidebar submenu toggle
    const submenuToggle = document.querySelector('.submenu-toggle');
    if (submenuToggle) {
        submenuToggle.addEventListener('click', (e) => {
            e.preventDefault();
            const submenu = submenuToggle.nextElementSibling;
            if (submenu && submenu.classList.contains('nav-submenu')) {
                submenu.classList.toggle('open');
            }
        });
    }

    // Live search for tables
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        const table = document.querySelector(searchInput.dataset.table);
        const noResultsRow = table ? table.querySelector('.no-results') : null;

        if (table) {
            searchInput.addEventListener('input', () => {
                const searchTerm = searchInput.value.toLowerCase();
                const rows = table.querySelectorAll('tbody tr:not(.no-results)');
                let visibleRows = 0;
                
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    if (text.includes(searchTerm)) {
                        row.style.display = '';
                        visibleRows++;
                    } else {
                        row.style.display = 'none';
                    }
                });

                if (noResultsRow) {
                    noResultsRow.style.display = visibleRows > 0 ? 'none' : '';
                }
            });
        }
    }
    
    // Existing sort functionality (no changes needed)
    // ...
});

function confirmDelete() {
    return confirm('Are you sure you want to delete this employee?');
}

function confirmDeleteItem() {
    return confirm('Are you sure you want to delete this item?');
}