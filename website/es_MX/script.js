
(function () {
  'use strict';

  const menuToggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.site-nav');

  if (menuToggle && nav) {
    menuToggle.addEventListener('click', function () {
      const expanded = menuToggle.getAttribute('aria-expanded') === 'true';
      menuToggle.setAttribute('aria-expanded', String(!expanded));
      nav.classList.toggle('open');
      document.body.classList.toggle('menu-open');
    });
  }

  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && reveals.length) {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });

    reveals.forEach(function (item) {
      observer.observe(item);
    });
  } else {
    reveals.forEach(function (item) {
      item.classList.add('visible');
    });
  }

  const form = document.querySelector('#waitlist-form');
  const success = document.querySelector('.success-message');
  if (form && success) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      success.classList.add('show');
      form.reset();
    });
  }

  const phoneDemo = document.querySelector('.phone-demo');

  if (phoneDemo) {
    const slides = Array.from(phoneDemo.querySelectorAll('.mockup-slide'));
    let currentIndex = 0;
  
    function clearSlideStates() {
      slides.forEach(function (slide) {
        slide.classList.remove('active');
        slide.classList.remove('leaving');
        slide.classList.remove('scroll-inside');
      
        const img = slide.querySelector('img');
      
        if (img) {
          img.style.removeProperty('--scroll-distance');
          img.style.animation = 'none';
          img.offsetHeight;
          img.style.animation = '';
        }
      });
    }
  
    function prepareLongScreen(slide) {
      const img = slide.querySelector('img');
      const clip = phoneDemo.querySelector('.phone-screen-clip');
    
      if (!img || !clip) {
        return false;
      }
    
      const scrollDistance = img.offsetHeight - clip.offsetHeight;
    
      if (scrollDistance > 8) {
        img.style.setProperty('--scroll-distance', `-${scrollDistance}px`);
        slide.classList.add('scroll-inside');
        return true;
      }
    
      return false;
    }
  
    function showNextSlide() {
      const currentSlide = slides[currentIndex];
      const nextIndex = (currentIndex + 1) % slides.length;
      const nextSlide = slides[nextIndex];
    
      currentSlide.classList.remove('active');
      currentSlide.classList.remove('scroll-inside');
      currentSlide.classList.add('leaving');
    
      nextSlide.classList.add('active');
    
      window.setTimeout(function () {
        currentSlide.classList.remove('leaving');
        prepareLongScreen(nextSlide);
      }, 800);
    
      currentIndex = nextIndex;
    }
  
    function startMockupCycle() {
      if (!slides.length) {
        return;
      }
    
      clearSlideStates();
      slides[0].classList.add('active');
      prepareLongScreen(slides[0]);
    
      window.setInterval(showNextSlide, 4200);
    }
  
    window.addEventListener('load', startMockupCycle);
  }

    const faqSearch = document.querySelector('#faq-search');
    const faqGroups = Array.from(document.querySelectorAll('[data-faq-group]'));
    const noResults = document.querySelector('.faq-no-results');
    const faqShell = document.querySelector('.faq-shell');
  
    if (!faqSearch || !faqGroups.length) {
      return;
    }

    function escapeRegExp(value) {
      return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function clearFaqHighlights() {
      document.querySelectorAll('mark.faq-highlight').forEach(function (highlight) {
        const parent = highlight.parentNode;

        if (!parent) {
          return;
        }

        parent.replaceChild(document.createTextNode(highlight.textContent), highlight);
        parent.normalize();
      });
    }

    function highlightFaqText(item, query) {
      const terms = query.split(/\s+/).filter(Boolean).map(escapeRegExp);

      if (!terms.length) {
        return;
      }

      const pattern = new RegExp('(' + terms.join('|') + ')', 'gi');
      const walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          if (!node.nodeValue.trim() || !pattern.test(node.nodeValue)) {
            pattern.lastIndex = 0;
            return NodeFilter.FILTER_REJECT;
          }

          pattern.lastIndex = 0;
          return NodeFilter.FILTER_ACCEPT;
        }
      });
      const textNodes = [];

      while (walker.nextNode()) {
        textNodes.push(walker.currentNode);
      }

      textNodes.forEach(function (node) {
        const fragment = document.createDocumentFragment();
        const parts = node.nodeValue.split(pattern);

        parts.forEach(function (part) {
          if (!part) {
            return;
          }

          if (pattern.test(part)) {
            const mark = document.createElement('mark');
            mark.className = 'faq-highlight';
            mark.textContent = part;
            fragment.appendChild(mark);
            pattern.lastIndex = 0;
            return;
          }

          pattern.lastIndex = 0;
          fragment.appendChild(document.createTextNode(part));
        });

        node.parentNode.replaceChild(fragment, node);
      });
    }

    function filterFaqItems() {
      const query = faqSearch.value.trim().toLowerCase();
      let totalMatches = 0;

      clearFaqHighlights();
    
      faqGroups.forEach(function (group) {
        const items = Array.from(group.querySelectorAll('.faq-item'));
        let groupMatches = 0;
      
        items.forEach(function (item) {
          const text = item.textContent.toLowerCase();
          const matches = !query || text.includes(query);
        
          item.classList.toggle('is-hidden', !matches);
        
          if (query && matches) {
            item.setAttribute('open', '');
            highlightFaqText(item, query);
          }
        
          if (!query) {
            item.removeAttribute('open');
          }
        
          if (matches) {
            groupMatches += 1;
            totalMatches += 1;
          }
        });
      
        group.classList.toggle('is-hidden', groupMatches === 0);
      });
    
      if (noResults) {
        noResults.hidden = totalMatches !== 0;
      }

      return totalMatches;
    }
  
    faqSearch.addEventListener('input', filterFaqItems);

    faqSearch.addEventListener('keydown', function (event) {
      const query = faqSearch.value.trim();

      if (event.key !== 'Enter' || !query || !faqShell) {
        return;
      }

      event.preventDefault();

      const totalMatches = filterFaqItems();
      const firstMatch = faqShell.querySelector('.faq-item:not(.is-hidden)');
      const scrollTarget = totalMatches ? firstMatch : noResults;

      if (scrollTarget) {
        scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
})();
