# App Store Metadata Character Limits

Reference for character limits across the Apple App Store and Google Play Store.

## Character Limits by Platform

| Field | Apple App Store | Google Play Store |
|-------|----------------|-------------------|
| App Name/Title | 30 chars | 30 chars |
| Subtitle | 30 chars | N/A |
| Short Description | N/A | 80 chars |
| Keywords Field | 100 chars | N/A |
| Promotional Text | 170 chars | N/A |
| Full Description | 4,000 chars | 4,000 chars |
| What's New | 4,000 chars | 500 chars |
| Developer Name | 50 chars | varies |

## Field Details

### App Name / Title

- **Limit**: 30 characters on both platforms
- **Indexed for search**: Yes (both platforms)
- **Tips**: Include your brand name and primary keyword. This is the
  highest-weight field for search ranking on both stores.

### Subtitle (iOS Only)

- **Limit**: 30 characters
- **Indexed for search**: Yes
- **Tips**: Use secondary keywords that complement the title. Do not repeat
  words already in the title. Appears directly below the app name in search
  results and on the product page.

### Short Description (Google Play Only)

- **Limit**: 80 characters
- **Indexed for search**: Yes
- **Tips**: Concise value proposition with 2-3 keywords. Visible on the store
  listing without expanding. Equivalent in purpose to the iOS subtitle but with
  more space.

### Keywords Field (iOS Only)

- **Limit**: 100 characters
- **Indexed for search**: Yes (hidden from users)
- **Tips**: Separate with commas, no spaces. Do not repeat words from title or
  subtitle. Use singular forms. Fill all 100 characters.

### Promotional Text (iOS Only)

- **Limit**: 170 characters
- **Indexed for search**: No
- **Tips**: Can be updated without a new app submission. Use for timely
  promotions, seasonal messages, or feature announcements. Appears above the
  description on the product page.

### Full Description

- **Limit**: 4,000 characters on both platforms
- **Indexed for search**: Only on Google Play (not on Apple App Store)
- **Tips**: For Google Play, include keywords naturally 3-5 times. For iOS,
  focus on conversion and readability since it does not affect search ranking.
  Structure with line breaks and bullet points.

### What's New (Release Notes)

- **Apple App Store limit**: 4,000 characters
- **Google Play Store limit**: 500 characters
- **Indexed for search**: No (both platforms)
- **Tips**: Highlight new features, bug fixes, and improvements. Users who read
  release notes are more likely to update. Keep it scannable.

### Developer Name

- **Apple App Store limit**: 50 characters
- **Google Play Store limit**: varies
- **Indexed for search**: Yes (both platforms)
- **Tips**: On Apple, the developer name is indexed and can influence search
  rankings. Some developers include a keyword in their developer account name,
  though Apple has tightened enforcement on this practice.

## Additional Metadata Fields

These fields are not character-limited in the traditional sense but are
important for ASO.

### Screenshots

| Platform | Minimum | Maximum | Recommended |
|----------|---------|---------|-------------|
| Apple App Store | 1 | 10 | 6-10 |
| Google Play Store | 2 | 8 | 6-8 |

- First 2-3 screenshots are visible without scrolling
- Landscape and portrait orientations are both supported
- Use captions and callout text to communicate features

### App Preview Video

| Platform | Max Length | Max Count |
|----------|-----------|-----------|
| Apple App Store | 30 seconds | 3 |
| Google Play Store | 30 seconds (promo video, YouTube link) | 1 |

### App Icon

- No character limit (visual asset)
- Must be provided in required dimensions for each platform
- Key factor in browse conversion rate
- Avoid text in the icon - it becomes unreadable at small sizes

### Ratings and Reviews

- No character limit for reviews (though platforms may enforce practical limits)
- Star ratings range from 1 to 5
- Average rating and total count are visible in search results
- Target: 4.0+ average, with as many ratings as possible

## Platform-Specific Notes

### Apple App Store
- Metadata changes (except promotional text) require a new app version submission
- Promotional text can be updated at any time without review
- Apple indexes: title, subtitle, keyword field, developer name, and in-app
  purchase names
- Apple does NOT index the description for search

### Google Play Store
- Metadata can be updated at any time without a new APK/AAB
- Google indexes: title, short description, full description, and developer name
- Google uses machine learning to understand app content beyond exact keyword
  matches
- Google Play allows A/B testing of store listings natively via Store Listing
  Experiments

## Validation Rules

When validating metadata, check for these common issues:

1. **Over limit**: Field exceeds maximum character count (will be rejected)
2. **Under-utilized**: Field is significantly shorter than the limit (missed opportunity)
3. **Keyword repetition**: Same word appears in multiple indexed fields (wasted space on iOS)
4. **Empty fields**: Optional fields left blank (missed opportunity)
5. **Special characters**: Some special characters consume more than 1 character in certain encodings
6. **Platform mismatch**: Using iOS-only fields for Android or vice versa
