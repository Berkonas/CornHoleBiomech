# Places Design Research

This is a working product document, not a visual mood board. It records the principles that materially shaped the application built in this repository. The downloaded book files that were already in the project were not consulted because their filenames indicate unofficial copies; they remain untouched.

## Sources Consulted

### Apple

- [Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/)
- [Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)
- [Search fields](https://developer.apple.com/design/human-interface-guidelines/search-fields)
- [Searching](https://developer.apple.com/design/human-interface-guidelines/searching)
- [Menus](https://developer.apple.com/design/human-interface-guidelines/menus)
- [Keyboards](https://developer.apple.com/design/human-interface-guidelines/keyboards)
- [Color](https://developer.apple.com/design/human-interface-guidelines/color)
- [Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode)
- [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
- [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility/)
- [NavigationSplitView](https://developer.apple.com/documentation/swiftui/navigationsplitview)
- [ModelContainer](https://developer.apple.com/documentation/swiftdata/modelcontainer)
- [MKLocalSearch](https://developer.apple.com/documentation/mapkit/mklocalsearch)
- [MKLocalSearchCompleter](https://developer.apple.com/documentation/mapkit/mklocalsearchcompleter)
- [LPMetadataProvider](https://developer.apple.com/documentation/linkpresentation/lpmetadataprovider)

### Product and interaction design

- Don Norman, [The Design of Everyday Things — revised edition preface](https://jnd.org/preface-design-of-everyday-things-revised-edition/) and [NN/g publisher description](https://www.nngroup.com/books/design-everyday-things-revised/)
- Steve Krug, [Don't Make Me Think](https://sensible.com/dont-make-me-think/)
- Jenifer Tidwell, Charles Brewer, and Aynne Valencia, [Designing Interfaces, 3rd Edition](https://www.oreilly.com/library/view/designing-interfaces-3rd/9781492051954/)
- Adam Wathan and Steve Schoger, [Refactoring UI](https://refactoringui.com/)
- Adham Dannaway, [Practical UI](https://www.practical-ui.com/)
- Marty Cagan / SVPG, [Product Model Concepts](https://www.svpg.com/product-model-concepts/) and [Inspired, 2nd Edition](https://www.svpg.com/books/inspired-how-to-create-tech-products-customers-love-2nd-edition/)
- Tim Brown / IDEO, [Change by Design](https://designthinking.ideo.com/resources/change-by-design) and [Introduction to design thinking](https://designthinking.ideo.com/introduction)
- Rob Fitzpatrick, [The Mom Test](https://www.momtestbook.com/)

Research was performed against the current Apple documentation available on August 30, 2026. The installed environment is Xcode 26.6, Swift 6.3.3, and the macOS 26.5 SDK. Xcode's license is not yet accepted on this machine, so package builds use the installed command-line Swift toolchain until that one-time local setup is completed.

## Principles and Application Decisions

### Make the conceptual model visible

Norman's discoverability, mapping, signifier, constraint, and feedback principles all point in the same direction: the interface should reveal what can be done and what just happened.

**Application decision:** The app uses the durable nouns people already think in: Collections contain Places; Categories describe what a Place is; Visits record what happened on a date. Favorite and visit status are independent. Add Place, Add Visit, Edit, Filter, Search, and link actions have visible labels or standard symbols with accessibility labels. Saving, importing, exporting, filtering, and network failure all produce visible feedback.

### Prefer recognition and scanning over recall

Krug argues for self-evident navigation and scan-friendly hierarchy. Apple's macOS guidance recommends using spacious displays to show more content in fewer nested levels while retaining comfortable density.

**Application decision:** A three-column `NavigationSplitView` keeps library scope, matching places, and the selected place visible together. Sidebar labels use conventional terms. Rows show only the facts needed to distinguish results: name, category, location, status, rating, favorite state, and last visit. `All Places` is always the first route.

### Put global search where Mac users expect it

Apple recommends a trailing toolbar search field for many macOS split-view apps, especially when results appear in one column while selection remains visible in another.

**Application decision:** One `Search places` field searches name, notes, category, city, neighborhood, cuisine, and tags, and combines with the current route and filters. Command-F focuses it.

### Keep frequent actions available without overcrowding

Apple positions the toolbar as the home for frequent, contextual commands and the menu bar as the complete command inventory. Tidwell's streamlined repetition and keyboard-only patterns favor short, repeatable workflows.

**Application decision:** The toolbar contains Add Place, contextual Add Visit, filters, sort, and search. File and Place menus duplicate important actions and expose shortcuts. Less frequent collection/category management and import/export stay in menus or focused sheets.

### Use progressive disclosure and incremental construction

Tidwell's deferred choices and incremental construction patterns, combined with Practical UI's interaction-cost guidance, argue against blocking simple work on optional detail.

**Application decision:** A place can be saved with only a name, collection, category, and status. Address, links, coordinates, notes, neighborhood, cuisine, price, tags, favorite, and rating are optional and live under a clearly labeled details section. A Visit requires only its default date; context, rating, and note are optional.

### Make filtering predictable and explainable

Reducing reliance on memory requires showing system state rather than hiding it inside menus.

**Application decision:** Collection/category/status routes and the explicit filter popover combine with AND semantics. Active explicit filters appear in a compact summary above the list with a visible Clear Filters action. Empty results explain whether the library or current filter is empty.

### Preserve safe exploration and personal data

Norman's constraints and feedback and Tidwell's safe exploration favor preventing irreversible surprises. For a local-first library, data durability outranks visual novelty.

**Application decision:** Place and populated-collection deletion require plain-language confirmation. Collection deletion states the number of places that will also be removed. Import validates the complete archive first, merges by stable IDs, skips duplicates, and never silently replaces the current database. The app never deletes its SwiftData store to repair migration problems.

### Let the platform own the visual system

Apple's current materials guidance places Liquid Glass in the functional navigation/control layer, not throughout content. Its color and Dark Mode guidance favors semantic system colors and respecting system appearance. Refactoring UI and Practical UI favor intentional hierarchy, consistent spacing, purposeful color, and de-emphasizing secondary content.

**Application decision:** Standard sidebar, toolbar, list, form, sheet, menu, and map components adopt the current system appearance automatically. Content uses normal backgrounds and separators, not decorative glass cards. System typography and semantic colors do most of the work; a restrained warm orange accent gives the default Nashville collection personality without becoming a theme.

### Accessibility is structural

Apple recommends semantic native controls, meaningful labels for symbols, keyboard navigation, sufficient contrast in both appearances, and testing with Full Keyboard Access and VoiceOver.

**Application decision:** Controls are native SwiftUI controls with text or accessibility labels, status never relies on color alone, list selection uses the system highlight, rating buttons announce their value, and all essential workflows are reachable from labeled controls or menus. The app follows system Dark Mode and increased-contrast behavior rather than supplying a separate appearance preference.

### Evaluate tasks, not compliments

The Mom Test's broader lesson is to prefer behavioral evidence over flattering opinions; IDEO and SVPG likewise emphasize solving an actual problem and validating outcomes before accumulating features.

**Application decision:** The product is evaluated against concrete tasks: save a place quickly, find it later, distinguish Restaurant from Dinner, add a second visit without losing the first, understand active filters, recover from metadata failure, and reconstruct a library from export. There is no dashboard of ornamental metrics and no AI feature.

## Rejected Ideas

- **A giant dashboard homepage:** it increases navigation distance without improving the core save/find/remember workflows.
- **A mobile tab bar or phone-style cards:** they waste Mac screen space and hide the stable library hierarchy.
- **Custom navigation or custom glass controls:** native sidebar, toolbar, menus, and split views provide better convention, accessibility, resizing, and current-system appearance.
- **Glass content cards, heavy gradients, and decorative shadows:** they compete with personal information and conflict with Apple's functional-layer guidance.
- **Hard-coded Nashville-only storage:** Nashville is seeded as the first Collection, not built into filtering or relationships.
- **One date or “last visit” field on Place:** Visit history is one-to-many; counts and dates are derived to avoid contradictory state.
- **Using visit type as category:** a restaurant can be visited for lunch, dinner, or date night; these answer different questions.
- **Requiring address, coordinates, rating, or notes before Save:** real-world metadata is often incomplete and should not block capture.
- **Google Maps HTML scraping:** the original URL is preserved; only reliable URL components, safe link metadata, and independent MapKit search are used.
- **Forcing coordinates or Location Services:** map display is conditional and search does not require the user's current location.
- **CloudKit, accounts, analytics, ads, tracking, or AI:** none help the private local-library job and all expand privacy or maintenance risk.
- **Silently replacing data on import or deleting the store after schema changes:** both violate the app's first priority, data integrity.

