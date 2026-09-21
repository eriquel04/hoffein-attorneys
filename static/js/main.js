const navbar = document.getElementById("navbar");

window.addEventListener("scroll", () => {
    if (navbar) navbar.classList.toggle("scrolled", window.scrollY > 50);
});

const revealElements = document.querySelectorAll(
    ".feature-card, .practice-card, .section-heading, .team-message"
);

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = "1";
            entry.target.style.transform = "translateY(0)";
        }
    });
}, { threshold: 0.15 });

const landingRevealElements = document.querySelectorAll("[data-reveal]");
const landingObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            landingObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.12 });

landingRevealElements.forEach(element => landingObserver.observe(element));

revealElements.forEach(element => {
    element.style.opacity = "0";
    element.style.transform = "translateY(40px)";
    element.style.transition = "opacity 0.8s ease, transform 0.8s ease";
    observer.observe(element);
});

const menuToggle = document.querySelector(".menu-toggle");
const siteNav = document.querySelector(".site-nav");

if (menuToggle && siteNav) {
    menuToggle.addEventListener("click", () => {
        const isOpen = siteNav.classList.toggle("is-open");
        menuToggle.setAttribute("aria-expanded", String(isOpen));
    });

    siteNav.querySelectorAll("a").forEach(link => {
        link.addEventListener("click", () => {
            siteNav.classList.remove("is-open");
            menuToggle.setAttribute("aria-expanded", "false");
        });
    });
}

const approachTabs = document.querySelectorAll(".approach-tab");
const approachPanels = document.querySelectorAll(".approach-panel");

approachTabs.forEach(tab => {
    tab.addEventListener("click", () => {
        const selectedApproach = tab.dataset.approach;

        approachTabs.forEach(item => {
            const isSelected = item === tab;
            item.classList.toggle("is-active", isSelected);
            item.setAttribute("aria-selected", String(isSelected));
        });

        approachPanels.forEach(panel => {
            panel.hidden = panel.dataset.panel !== selectedApproach;
            panel.classList.toggle("is-active", !panel.hidden);
        });
    });
});

const portalPage = document.querySelector(".portal-page");
const portalTabs = document.querySelectorAll(".portal-tab");
const portalMenuItems = document.querySelectorAll("[data-portal-menu]");
const portalMenuToggle = document.querySelector(".portal-menu-toggle");

if (portalPage && portalMenuToggle) {
    portalMenuToggle.addEventListener("click", () => {
        portalPage.classList.toggle("sidebar-open");
    });
}

if (portalPage && (portalTabs.length || portalMenuItems.length)) {
    const portalRole = portalPage.dataset.portalRole;
    const sectionView = (heading) => {
        const title = heading.toLowerCase();

        if (title.includes("case")) return "cases";
        if (title.includes("client")) return "clients";
        if (title.includes("appointment")) return "appointments";
        if (title.includes("message")) return "messages";

        if (portalRole === "admin") {
            if (title.includes("document")) return "documents";
            if (title.includes("appointment") || title.includes("message")) return "communication";
            return "overview";
        }

        if (title.includes("document") || title.includes("upload")) return "documents";
        if (title.includes("appointment") || title.includes("message")) return "communication";
        return "overview";
    };

    const portalSections = document.querySelectorAll(".dashboard-section");
    const portalSummaries = document.querySelectorAll(".portal-summary");

    const showPortalView = (selectedView, selectedTab, selectedMenuItem) => {
        portalTabs.forEach(item => {
            const isSelected = item === selectedTab;
            item.classList.toggle("is-active", isSelected);
            item.setAttribute("aria-selected", String(isSelected));
        });

        portalMenuItems.forEach(item => {
            item.classList.toggle("is-active", item === selectedMenuItem);
        });

        portalSummaries.forEach(summary => {
            summary.hidden = selectedView !== "overview";
        });

        portalSections.forEach(section => {
            const heading = section.querySelector("h2");
            const sectionName = section.dataset.portalSection
                || (heading ? sectionView(heading.textContent) : "");
            const isCommunicationView = selectedView === "communication"
                && ["appointments", "messages"].includes(sectionName);
            section.hidden = !heading || (sectionName !== selectedView && !isCommunicationView);
        });
    };

    portalTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const selectedView = tab.dataset.portalView;

            showPortalView(selectedView, tab);

            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    });

    portalMenuItems.forEach(menuItem => {
        menuItem.addEventListener("click", event => {
            event.preventDefault();

            const selectedView = menuItem.dataset.portalMenu;
            const matchingTab = Array.from(portalTabs).find(
                tab => tab.dataset.portalView === selectedView
                    || (selectedView === "appointments" && tab.dataset.portalView === "communication")
                    || (selectedView === "messages" && tab.dataset.portalView === "communication")
            );

            showPortalView(selectedView, matchingTab, menuItem);

            if (portalPage.classList.contains("sidebar-open")) {
                portalPage.classList.remove("sidebar-open");
            }

            const targetSection = document.querySelector(
                `[data-portal-section="${selectedView}"]`
            );
            const scrollTarget = document.querySelector(".portal-switcher") || targetSection;

            if (scrollTarget) {
                window.scrollTo({
                    top: scrollTarget.offsetTop - 115,
                    behavior: "smooth"
                });
            }
        });
    });

    document.querySelectorAll("[data-portal-menu-trigger]").forEach(trigger => {
        trigger.addEventListener("click", event => {
            event.preventDefault();
            const targetView = trigger.dataset.portalMenuTrigger;
            const matchingMenuItem = Array.from(portalMenuItems).find(
                item => item.dataset.portalMenu === targetView
            );

            if (matchingMenuItem) {
                matchingMenuItem.click();
            }
        });
    });

    const searchView = (() => {
        const params = new URLSearchParams(window.location.search);

        if (params.has("client_id")) return "clients";
        if (params.has("lawyer_id")) return "lawyers";
        if (params.has("case_id")) return "cases";
        if (params.has("document_client_id")) return "documents";
        if (params.has("appointment_id")) return "appointments";

        return "overview";
    })();

    const initialMenuItem = Array.from(portalMenuItems).find(
        item => item.dataset.portalMenu === searchView
    ) || portalMenuItems[0];
    const initialTab = Array.from(portalTabs).find(
        tab => tab.dataset.portalView === searchView
    ) || portalTabs[0];

    showPortalView(searchView, initialTab, initialMenuItem);
}

const hero = document.querySelector(".hero");
const glow = document.querySelector(".hero-glow");

if (hero && glow) {
    hero.addEventListener("mousemove", (event) => {
        const x = (event.clientX / window.innerWidth - 0.5) * 30;
        const y = (event.clientY / window.innerHeight - 0.5) * 30;
        glow.style.transform = `translate(${x}px, ${y}px)`;
    });
}

const sections = document.querySelectorAll("section[id]");
const navLinks = document.querySelectorAll("nav a[href^='#']");

window.addEventListener("scroll", () => {
    let current = "";

    sections.forEach(section => {
        const sectionTop = section.offsetTop - 150;
        if (window.scrollY >= sectionTop) {
            current = section.getAttribute("id");
        }
    });

    navLinks.forEach(link => {
        link.classList.toggle(
            "active",
            link.getAttribute("href") === `#${current}`
        );
    });
});

document.querySelectorAll(
    ".primary-btn, .secondary-btn, .start-btn, .login-btn"
).forEach(button => {
    button.addEventListener("click", () => {
        button.style.transform = "scale(0.96)";
        setTimeout(() => button.style.transform = "", 120);
    });
});

const requestedDocumentSelect = document.getElementById("request_id");
const clientCaseSelect = document.getElementById("case_id");

if (requestedDocumentSelect && clientCaseSelect) {
    requestedDocumentSelect.addEventListener("change", () => {
        const selectedRequest = requestedDocumentSelect.selectedOptions[0];
        const requestedCaseId = selectedRequest.dataset.caseId;

        if (requestedCaseId) {
            clientCaseSelect.value = requestedCaseId;
        }
    });
}

document.querySelectorAll("[data-document-filter]").forEach(filterButton => {
    filterButton.addEventListener("click", () => {
        const selectedStatus = filterButton.dataset.documentFilter;

        document.querySelectorAll("[data-document-filter]").forEach(button => {
            button.classList.toggle("is-active", button === filterButton);
        });

        document.querySelectorAll("[data-document-status]").forEach(documentCard => {
            documentCard.hidden = selectedStatus !== "all"
                && documentCard.dataset.documentStatus !== selectedStatus;
        });
    });
});
