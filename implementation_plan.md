# Implementation Plan - Mobile UX & Performance

This plan addresses the user's feedback regarding mobile navigation (swipes vs arrows), UI overlap issues, and explains the performance metrics seen in PageSpeed Insights.

## User Objectives
1.  **Mobile Navigation**: Replace arrow navigation with swipe gestures on mobile devices.
2.  **UI Layout**: Fix the carousel indicators (dots) overlapping the text content on mobile.
3.  **Performance Understanding**: Address why third-party scripts (Ads, GTM, Tailwind) are flagging as blocking tasks.

## Proposed Changes

### 1. Mobile Carousel UX (`templates/index.html`)

#### A. Implement Swipe Gestures
-   **File**: `templates/index.html`
-   **Action**: Update the embedded JavaScript for the carousel.
-   **Logic**:
    -   Add `touchstart` and `touchend` event listeners to the carousel container.
    -   Capture X coordinates.
    -   Calculate difference; if > 50px, trigger `changeSlide(1)` or `changeSlide(-1)`.
    -   Pause auto-rotation on touch interaction.

#### B. Hide Arrows on Mobile
-   **File**: `templates/index.html`
-   **Action**: Add Tailwind utility classes to the arrow buttons.
-   **Change**: `<button ... class="...">` -> `<button ... class="hidden md:block ...">`.

#### C. Fix Indicator Overlap
-   **File**: `templates/index.html`
-   **Action**: Increase bottom padding of the text container inside the slide.
-   **Change**: `<div class="bg-black/40 ... p-4 md:p-8">` -> `<div class="bg-black/40 ... p-4 pb-12 md:p-8">`.
-   **Reasoning**: This pushes the text content up, creating a reserved "safe zone" at the bottom for the absolute-positioned dots, preventing visual collision.

### 2. Performance Analysis (Explanation)
-   **Tailwind CDN (`cdn.tailwindcss.com`)**: This script compiles CSS in the browser. It causes a ~60-100ms delay and "Layout Shift" warnings because it runs on the main thread.
    -   *Recommendation*: For a production site, we should eventually set up a CSS build step, but for the current "drop-in" editing workflow, the CDN is a necessary trade-off.
-   **Google Ads (`adsbygoogle.js`)**: These are notoriously heavy. They load dynamic auctions and creatives. 700ms+ is typical.
-   **Google Funding Choices**: The consent popup. It must block interaction until consent is handled, hence the "Blocking" status.

## Verification
1.  **Mobile View**: Verify arrows are gone.
2.  **Interaction**: Verify dragging/swiping the image changes slides.
3.  **Visuals**: Verify the text summary ("The Gist") does not sit underneath the white dots.
