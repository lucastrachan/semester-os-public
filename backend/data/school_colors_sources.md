# School colour sources and checks

Generated 2026-10-17 by the colour research agent. Data file: `backend/data/school_colors.json` (102 domains, 100 distinct institutions).

Rule: a school is listed only if its colour came from an official school page or brand guide (found through search, values extracted from the school's own pages or PDFs). 'hex given' means the official page states the hex. Where only Pantone was stated the row says CONVERTED. Third-party colour sites were not used as sources. Most hex values were read through a search summary of the official page rather than the raw page, so re-open the source URL before treating any single value as final. Unit-level sources (college or design-system pages on the school's own domain) are marked in the note.

Contrast = WCAG 2.x ratio of the primary against white and against #10131A. 'AA text' lists which of the two reaches 4.5:1 (informational; the app picks its own text colour).

Flags: NEAR-BLACK = relative luminance < 0.02, very dark = < 0.04, NEAR-WHITE = > 0.70. A human should decide on flagged rows.

## Flagged primaries (human decision needed)

- auburn.edu (Auburn University) #0B2341: NEAR-BLACK (white 15.78, #10131A 1.18)
- samford.edu (Samford University) #0C2340: NEAR-BLACK (white 15.79, #10131A 1.18)
- southalabama.edu (University of South Alabama) #00205B: NEAR-BLACK (white 15.47, #10131A 1.20)
- aamu.edu (Alabama A&M University) #61162D: very dark (white 12.64, #10131A 1.47)
- shc.edu (Spring Hill College) #3D1951: very dark (white 14.42, #10131A 1.29)
- lsu.edu (Louisiana State University) #461D7C: very dark (white 12.16, #10131A 1.53)
- msstate.edu (Mississippi State University) #5D1725: very dark (white 13.01, #10131A 1.43)
- tamu.edu (Texas A&M University - College Station) #500000: NEAR-BLACK (white 15.66, #10131A 1.19)
- sc.edu (University of South Carolina) #73000A: very dark (white 12.12, #10131A 1.53)
- vanderbilt.edu (Vanderbilt University) #1C1C1C: NEAR-BLACK (white 17.04, #10131A 1.09)
- duke.edu (Duke University) #012169: very dark (white 14.76, #10131A 1.26)
- virginia.edu (University of Virginia, Charlottesville) #232D4B: very dark (white 13.56, #10131A 1.37)
- nd.edu (University of Notre Dame) #0C2340: NEAR-BLACK (white 15.79, #10131A 1.18)
- umich.edu (University of Michigan - Ann Arbor) #00274C: NEAR-BLACK (white 15.06, #10131A 1.23)
- umn.edu (University of Minnesota) #6D001F: very dark (white 12.57, #10131A 1.48)
- psu.edu (Pennsylvania State University) #001E44: NEAR-BLACK (white 16.55, #10131A 1.12)
- tcu.edu (Texas Christian University) #4D1979: very dark (white 12.13, #10131A 1.53)
- berkeley.edu (University of California, Berkeley) #002676: very dark (white 13.65, #10131A 1.36)
- uwyo.edu (University of Wyoming) #492F24: very dark (white 12.24, #10131A 1.52)
- usu.edu (Utah State University) #0F2439: NEAR-BLACK (white 15.77, #10131A 1.18)
- fiu.edu (Florida International University) #081E3F: NEAR-BLACK (white 16.56, #10131A 1.12)
- upenn.edu (University of Pennsylvania) #011F5B: NEAR-BLACK (white 15.57, #10131A 1.19)
- mit.edu (Massachusetts Institute of Technology) #750014: very dark (white 11.89, #10131A 1.56)
- jhu.edu (Johns Hopkins University) #002D72: very dark (white 12.98, #10131A 1.43)
- georgetown.edu (Georgetown University) #041E42: NEAR-BLACK (white 16.54, #10131A 1.12)
- rice.edu (Rice University) #00205B: NEAR-BLACK (white 15.47, #10131A 1.20)
- emory.edu (Emory University) #012169: very dark (white 14.76, #10131A 1.26)
- yale.edu (Yale University) #00356B: very dark (white 12.20, #10131A 1.52)

## Primaries where neither white nor #10131A reaches 4.5:1


## Verified schools (102)

### ua.edu : The University of Alabama
- primary #9E1B32, secondary #828A8F
- source: https://brand.ua.edu/color/
- derivation: hex given (Crimson Flame, PMS 201; secondary Capstone Gray, PMS 430)
- contrast on primary: white 7.90, #10131A 2.35; AA text (4.5:1): white

### auburn.edu : Auburn University
- primary #0B2341, secondary #E86100
- source: https://ocm.auburn.edu/brand-center/colors.php
- derivation: hex given (Auburn Blue PMS 289; Auburn Orange PMS 158)
- contrast on primary: white 15.78, #10131A 1.18; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Older Auburn web template page lists #03244D/#DD550C; brand center is the current source.

### uab.edu : University of Alabama at Birmingham
- primary #1A5632, secondary #FDB913
- source: https://bb.uab.edu/brandguide/university/colors
- derivation: hex given (UAB Green PMS 357; UAB Gold PMS 7549)
- contrast on primary: white 8.67, #10131A 2.14; AA text (4.5:1): white

### samford.edu : Samford University
- primary #0C2340, secondary #BD1F2D
- source: https://www.samford.edu/Templates/
- derivation: hex given on Samford web template page as conversion of PMS 289 navy / PMS 200 red
- contrast on primary: white 15.79, #10131A 1.18; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Brand Standards PDF (samford.edu/departments/files/Marketing/Samford-Brand-Standards.pdf) lists PMS only.

### southalabama.edu : University of South Alabama
- primary #00205B, secondary #BF0D3E
- source: https://www.southalabama.edu/departments/publicrelations/brand/
- derivation: hex given (USA Blue PMS 281; USA Red PMS 193)
- contrast on primary: white 15.47, #10131A 1.20; AA text (4.5:1): white; FLAG: NEAR-BLACK

### aamu.edu : Alabama A&M University
- primary #61162D, secondary null
- source: https://www.aamu.edu/about/administrative-offices/marketing-communication-advancement/marketing-public-relations/brand-guidelines.html
- derivation: hex given (digital maroon; print PMS 7421 C)
- contrast on primary: white 12.64, #10131A 1.47; AA text (4.5:1): white; FLAG: very dark
- note: Secondary left null: white/black hex not stated.

### alasu.edu : Alabama State University
- primary #C99700, secondary #000000
- source: https://www.alasu.edu/administration/institutional-effectiveness/marketing-and-strategic-communications/brand-guidelines.pdf
- derivation: hex given for ASU Old Gold (PMS 117); secondary black: guide says use 100% black for digital (#000000 is inferred, not printed)
- contrast on primary: white 2.65, #10131A 7.00; AA text (4.5:1): #10131A
- note: Official colours are Old Gold and Black; gold chosen as primary because black as a theme colour is near-black.

### uah.edu : University of Alabama at Huntsville
- primary #0058A4, secondary #FDDA24
- source: https://www.uah.edu/omc/resources/brand
- derivation: hex given (UAH Blue PMS 293C; yellow accent)
- contrast on primary: white 7.16, #10131A 2.59; AA text (4.5:1): white
- note: UAH documents disagree: 2024 anniversary guide lists blue #0077C8 (PMS 3005C). Current brand page value used.

### una.edu : University of North Alabama
- primary #592B8A, secondary #FFB92A
- source: https://www.una.edu/emdc/brand/colors.html
- derivation: hex given (PMS 268c / PMS 1235c)
- contrast on primary: white 9.83, #10131A 1.89; AA text (4.5:1): white

### shc.edu : Spring Hill College
- primary #3D1951, secondary #A8A8A9
- source: https://www.shc.edu/wp-content/uploads/2025/07/SHC-OneSheetGuide.pdf
- derivation: hex given (SHC Purple PMS 2627; Cool Gray 6)
- contrast on primary: white 14.42, #10131A 1.29; AA text (4.5:1): white; FLAG: very dark

### uga.edu : University of Georgia
- primary #BA0C2F, secondary #000000
- source: https://brand.uga.edu/visual-identity/visual-style/
- derivation: hex given (Bulldog Red PMS 200; Arch Black)
- contrast on primary: white 6.60, #10131A 2.82; AA text (4.5:1): white

### ufl.edu : University of Florida
- primary #FA4616, secondary #0021A5
- source: https://brandcenter.ufl.edu/colors/
- derivation: hex given (orange PMS 172; blue PMS 287)
- contrast on primary: white 3.53, #10131A 5.27; AA text (4.5:1): #10131A
- note: Legacy orange #FF4A00 still appears on old UF sites.

### utk.edu : University of Tennessee, Knoxville
- primary #FF8200, secondary null
- source: https://brand.utk.edu/standards/colors/
- derivation: hex given (Tennessee Orange, PMS 151)
- contrast on primary: white 2.49, #10131A 7.47; AA text (4.5:1): #10131A
- note: UT says this orange fails accessibility for small text.

### uky.edu : University of Kentucky
- primary #0033A0, secondary null
- source: https://webgov.uky.edu/standards/
- derivation: hex given on UK web standards (Wildcat Blue); brand site names PMS 286 (https://brand.uky.edu/our-identity/color-palette)
- contrast on primary: white 10.60, #10131A 1.75; AA text (4.5:1): white

### lsu.edu : Louisiana State University
- primary #461D7C, secondary #FDD023
- source: https://www.lsu.edu/communications/files/brand-guide.pdf
- derivation: hex given (LSU Purple PMS 268c; LSU Gold PMS 123c)
- contrast on primary: white 12.16, #10131A 1.53; AA text (4.5:1): white; FLAG: very dark

### olemiss.edu : University of Mississippi
- primary #C8102E, secondary #13294B
- source: https://olemiss.edu/csm/licensing/
- derivation: CONVERTED from Pantone (official page lists PMS 186C red and PMS 2767C navy, no hex); standard Pantone-to-hex conversions
- contrast on primary: white 5.88, #10131A 3.16; AA text (4.5:1): white
- note: No hex on the official page, medium confidence. Ole Miss navy is near-black.

### msstate.edu : Mississippi State University
- primary #5D1725, secondary null
- source: https://brand.msstate.edu/assets/materials/msstate_colors.pdf
- derivation: hex given (MSSTATE Maroon, PMS 505)
- contrast on primary: white 13.01, #10131A 1.43; AA text (4.5:1): white; FLAG: very dark
- note: Older trademark FAQ says #660000; palette PDF is more specific.

### uark.edu : University of Arkansas - Fayetteville
- primary #9D2235, secondary null
- source: https://brand.uark.edu/graphic-identity/official-colors.php
- derivation: hex given (Razorback Red PMS 201)
- contrast on primary: white 7.74, #10131A 2.40; AA text (4.5:1): white
- note: Walton College page gives RGB 161/0/47 for the same name; university brand PDF and web colors page say #9D2235.

### missouri.edu : University of Missouri
- primary #FDB719, secondary #000000
- source: https://brand.missouri.edu/brand-visuals/colors/
- derivation: hex given (Mizzou Gold PMS 124 C; Tiger Paw Black)
- contrast on primary: white 1.76, #10131A 10.59; AA text (4.5:1): #10131A

### tamu.edu : Texas A&M University - College Station
- primary #500000, secondary null
- source: https://marcomm.tamu.edu/creative-platform/visual-style/web-branding/
- derivation: hex given for web (Aggie Maroon #500000, confirmed on other TAMU brand pages)
- contrast on primary: white 15.66, #10131A 1.19; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: TAMU notes maroon has no exact RGB for print.

### utexas.edu : The University of Texas at Austin
- primary #BF5700, secondary null
- source: https://umac.utexas.edu/brand-center/colors/
- derivation: hex given (Burnt Orange PMS 159)
- contrast on primary: white 4.59, #10131A 4.05; AA text (4.5:1): white

### ou.edu : University of Oklahoma
- primary #841617, secondary null
- source: https://www.ou.edu/brand/creative-platform/design-system/colors
- derivation: hex given (Oklahoma Crimson, PMS 201)
- contrast on primary: white 9.96, #10131A 1.87; AA text (4.5:1): white
- note: Cream is not approved for web.

### sc.edu : University of South Carolina
- primary #73000A, secondary #000000
- source: https://sc.edu/about/offices_and_divisions/communications/toolbox/colors/
- derivation: hex given (Garnet PMS 202; Black)
- contrast on primary: white 12.12, #10131A 1.53; AA text (4.5:1): white; FLAG: very dark
- note: Garnet is very dark.

### vanderbilt.edu : Vanderbilt University
- primary #1C1C1C, secondary #CFAE70
- source: https://brand.vanderbilt.edu/color/
- derivation: hex given (Black #1C1C1C); secondary is the Athletics flat gold PMS 4024 C #CFAE70 from https://brand.vanderbilt.edu/athletics/
- contrast on primary: white 17.04, #10131A 1.09; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Official primary colours are black and gold; black is near-black, a human may prefer the gold as theme primary.

### clemson.edu : Clemson University
- primary #F56600, secondary #522D80
- source: https://www.clemson.edu/brand/web/color.html
- derivation: hex given in the web contrast chart (Clemson Orange, Regalia)
- contrast on primary: white 3.10, #10131A 6.00; AA text (4.5:1): #10131A
- note: An old Clemson blog lists orange #F66733; web guidelines page used.

### fsu.edu : Florida State University
- primary #782F40, secondary #CEB888
- source: https://brand.fsu.edu/web/colors
- derivation: hex given (Garnet, Gold)
- contrast on primary: white 9.21, #10131A 2.02; AA text (4.5:1): white

### miami.edu : University of Miami
- primary #F47321, secondary #005030
- source: https://webcomm.miami.edu/resources/identity/color/index.html
- derivation: hex given for digital (orange PMS 158; green PMS 3435)
- contrast on primary: white 2.87, #10131A 6.48; AA text (4.5:1): #10131A
- note: Site also lists an accessible dark orange #C35009 for text.

### duke.edu : Duke University
- primary #012169, secondary #00539B
- source: https://brand.duke.edu/colors/
- derivation: hex given (Duke Navy Blue PMS 280; Duke Royal Blue PMS 287)
- contrast on primary: white 14.76, #10131A 1.26; AA text (4.5:1): white; FLAG: very dark
- note: Older Duke web guidance used #001A57. Navy is dark.

### unc.edu : University of North Carolina at Chapel Hill
- primary #4B9CD3, secondary null
- source: https://identity.unc.edu/brand/color/
- derivation: hex given (Carolina Blue PMS 542 C)
- contrast on primary: white 3.00, #10131A 6.19; AA text (4.5:1): #10131A
- note: Light blue: white text fails 4.5:1.

### ncsu.edu : North Carolina State University
- primary #CC0000, secondary #000000
- source: https://brand.ncsu.edu/color/
- derivation: hex given (Wolfpack Red PMS 186 C; Wolfpack Black)
- contrast on primary: white 5.89, #10131A 3.16; AA text (4.5:1): white

### virginia.edu : University of Virginia, Charlottesville
- primary #232D4B, secondary #E57200
- source: https://brand.virginia.edu/design-assets/colors
- derivation: hex given (UVA Blue; UVA Orange PMS 158C)
- contrast on primary: white 13.56, #10131A 1.37; AA text (4.5:1): white; FLAG: very dark
- note: UVA Blue is dark.

### vt.edu : Virginia Tech
- primary #861F41, secondary #E87722
- source: https://vetmed.vt.edu/content/dam/vetmed_vt_edu/news/college-brand-guide/VMCVM_BrandGuidelines.pdf
- derivation: hex given in a Virginia Tech college brand guide reproducing the university palette (Chicago Maroon PMS 208; Burnt Orange PMS 158); central page https://brand.vt.edu/identity/color.html lists names and PMS only
- contrast on primary: white 9.19, #10131A 2.02; AA text (4.5:1): white
- note: Hex source is a college-level guide on vt.edu, not the central brand page.

### wfu.edu : Wake Forest University
- primary #9E7E38, secondary #000000
- source: https://brand.wfu.edu/our-brand-identity/color-patterns-papers/
- derivation: hex given (Old Gold PMS 871; Black)
- contrast on primary: white 3.82, #10131A 4.86; AA text (4.5:1): #10131A
- note: Brand guide also gives a darker web-text gold #8C6D2C.

### gatech.edu : Georgia Institute of Technology
- primary #B3A369, secondary #003057
- source: https://brand.gatech.edu/sites/default/files/documents/gtd8_body_styles_guide.pdf
- derivation: hex given (Tech Gold in GT web style guide; Navy from GT video guidelines https://brand.gatech.edu/our-look/video)
- contrast on primary: white 2.51, #10131A 7.40; AA text (4.5:1): #10131A
- note: CONFLICT: https://brand.gatech.edu/our-look/colors lists gold #B39051 and navy #051E39. Web values used.

### louisville.edu : University of Louisville
- primary #AD0000, secondary #000000
- source: https://brand.louisville.edu/visual/color
- derivation: hex given (Cardinal Red web value, PMS 1797; Black)
- contrast on primary: white 7.56, #10131A 2.46; AA text (4.5:1): white
- note: UofL says its screen reds are deliberately darker than print.

### nd.edu : University of Notre Dame
- primary #0C2340, secondary #AE9142
- source: https://onmessage.nd.edu/university-branding/colors/
- derivation: hex given (Blue PMS 289; metallic gold PMS 10127 screen value)
- contrast on primary: white 15.79, #10131A 1.18; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Athletics guide uses gold #C99700.

### pitt.edu : University of Pittsburgh
- primary #003594, secondary #FFB81C
- source: https://www.brand.pitt.edu/brand-elements/color-palettes
- derivation: hex given (Royal Blue PMS 661C; Gold PMS 1235C)
- contrast on primary: white 10.84, #10131A 1.71; AA text (4.5:1): white

### syr.edu : Syracuse University
- primary #F76900, secondary null
- source: https://designsystem.syr.edu/documentation/design-tokens/color/
- derivation: hex given in the Syracuse design system tokens (primary orange)
- contrast on primary: white 3.01, #10131A 6.17; AA text (4.5:1): #10131A
- note: No official print Pantone confirmed; hex comes from the university design system.

### illinois.edu : University of Illinois Urbana-Champaign
- primary #FF5F05, secondary #13294B
- source: https://brand.illinois.edu/visual-identity/color
- derivation: hex given (Illini Orange PMS 1655; Illini Blue PMS 2767)
- contrast on primary: white 3.05, #10131A 6.10; AA text (4.5:1): #10131A

### iu.edu : Indiana University
- primary #990000, secondary null
- source: https://www.iu.edu/brand/iu-brand/visual-identity/color.html
- derivation: hex given (Crimson PMS 201C)
- contrast on primary: white 8.92, #10131A 2.08; AA text (4.5:1): white
- note: Cream #EDEBEB is the other official colour but is near-white; omitted as secondary.

### indiana.edu : Indiana University - Bloomington
- primary #990000, secondary null
- source: https://www.iu.edu/brand/iu-brand/visual-identity/color.html
- derivation: hex given (Crimson PMS 201C); same Indiana University brand as iu.edu
- contrast on primary: white 8.92, #10131A 2.08; AA text (4.5:1): white

### uiowa.edu : University of Iowa
- primary #FFCD00, secondary #000000
- source: https://brand.uiowa.edu/color
- derivation: hex given (PMS 116 C gold; Black)
- contrast on primary: white 1.50, #10131A 12.37; AA text (4.5:1): #10131A

### umd.edu : University of Maryland, College Park
- primary #E21833, secondary #FFD200
- source: https://brand.umd.edu/visual-identity/colors
- derivation: hex given (Maryland Red; Maryland Gold)
- contrast on primary: white 4.76, #10131A 3.90; AA text (4.5:1): white

### umich.edu : University of Michigan - Ann Arbor
- primary #00274C, secondary #FFCB05
- source: https://brand.umich.edu/design-resources/colors/
- derivation: hex given (Michigan Blue PMS 282; Maize PMS 7406)
- contrast on primary: white 15.06, #10131A 1.23; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Blue is dark.

### msu.edu : Michigan State University
- primary #18453B, secondary null
- source: https://brand.msu.edu/visual/color-palette
- derivation: hex given (Spartan Green, PMS 567)
- contrast on primary: white 10.75, #10131A 1.73; AA text (4.5:1): white

### umn.edu : University of Minnesota
- primary #6D001F, secondary #FFCC33
- source: https://umarcomm.umn.edu/blog/2026/09/24/fresh-brand-colors-and-typeface
- derivation: hex given for the NEW maroon (announced Sept 2026, PMS 195 C); gold from https://umarcomm.umn.edu/resources/colors-and-type
- contrast on primary: white 12.57, #10131A 1.48; AA text (4.5:1): white; FLAG: very dark
- note: Maroon changed in Sept 2026; older pages still show #7A0019. Maroon is very dark.

### unl.edu : University of Nebraska, Lincoln
- primary #D00000, secondary #F5F1E7
- source: https://ucomm.unl.edu/brand/templates-assets/colors/
- derivation: hex given (Scarlet PMS 186CP; Cream)
- contrast on primary: white 5.70, #10131A 3.26; AA text (4.5:1): white
- note: Cream secondary is near-white.

### northwestern.edu : Northwestern University
- primary #4E2A84, secondary null
- source: https://www.northwestern.edu/brand/visual-identity/color-palettes/
- derivation: hex given (Northwestern Purple)
- contrast on primary: white 10.56, #10131A 1.76; AA text (4.5:1): white
- note: Kellogg page uses #4F2582; university palette used.

### osu.edu : Ohio State University - Columbus
- primary #BA0C2F, secondary #A7B1B7
- source: https://bux.osu.edu/color/primary-colors/
- derivation: hex given (Scarlet PMS 200; Gray PMS 429)
- contrast on primary: white 6.60, #10131A 2.82; AA text (4.5:1): white

### uoregon.edu : University of Oregon
- primary #007030, secondary #FEE11A
- source: https://communications.uoregon.edu/uo-brand/visual-identity/colors
- derivation: hex given (UO Green PMS 356; UO Yellow PMS 107)
- contrast on primary: white 6.25, #10131A 2.97; AA text (4.5:1): white
- note: UO accessibility page mentions an Aug 2026 palette update; primaries unchanged in what was retrieved.

### psu.edu : Pennsylvania State University
- primary #001E44, secondary #1E407C
- source: https://brand.psu.edu/visual-identity-standards/color-and-the-mark
- derivation: hex given (Nittany Navy PMS 282; Beaver Blue PMS 287)
- contrast on primary: white 16.55, #10131A 1.12; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Navy is very dark.

### purdue.edu : Purdue University
- primary #CFB991, secondary #000000
- source: https://www.purdue.edu/brand-studio/brand/visual-identity/
- derivation: hex given (Boilermaker Gold; Black)
- contrast on primary: white 1.91, #10131A 9.74; AA text (4.5:1): #10131A
- note: Gold is light.

### rutgers.edu : Rutgers University
- primary #CC0033, secondary null
- source: https://communications.rutgers.edu/sites/default/files/rutgers_visual_identity_system_user_guide.pdf
- derivation: hex given (Rutgers Scarlet PMS 186)
- contrast on primary: white 5.81, #10131A 3.20; AA text (4.5:1): white

### ucla.edu : University of California, Los Angeles
- primary #2774AE, secondary #FFD100
- source: https://brand.ucla.edu/identity/colors
- derivation: hex given (UCLA Blue PMS 2383C; UCLA Gold)
- contrast on primary: white 5.01, #10131A 3.71; AA text (4.5:1): white

### usc.edu : University of Southern California
- primary #990000, secondary #FFCC00
- source: https://identity.usc.edu/identity/color/
- derivation: hex given (Cardinal PMS 201 C; Gold PMS 123 C)
- contrast on primary: white 8.92, #10131A 2.08; AA text (4.5:1): white

### washington.edu : University of Washington
- primary #4B2E83, secondary #FFC700
- source: https://www.washington.edu/brand/brand-elements/colors/
- derivation: hex given (Spirit Purple; Spirit Gold)
- contrast on primary: white 10.41, #10131A 1.79; AA text (4.5:1): white
- note: CONFLICT: the UW brand page also labels #32006E as Husky Purple and #B7A57A as Husky Gold. Spirit colours used (web and accessibility palette).

### uw.edu : University of Washington
- primary #4B2E83, secondary #FFC700
- source: https://www.washington.edu/brand/brand-elements/colors/
- derivation: hex given (Spirit Purple; Spirit Gold); same University of Washington brand as washington.edu
- contrast on primary: white 10.41, #10131A 1.79; AA text (4.5:1): white
- note: See washington.edu conflict note.

### wisc.edu : University of Wisconsin - Madison
- primary #C5050C, secondary #9B0000
- source: https://brand.wisc.edu/visual-identity/colors/
- derivation: hex given (Badger Red PMS 200 C; Dark Red)
- contrast on primary: white 6.17, #10131A 3.01; AA text (4.5:1): white

### arizona.edu : University of Arizona
- primary #AB0520, secondary #0C234B
- source: https://marcom.arizona.edu/brand-guidelines/colors
- derivation: hex given (Arizona Red PMS 200 C; Arizona Blue PMS 281 C)
- contrast on primary: white 7.57, #10131A 2.45; AA text (4.5:1): white

### asu.edu : Arizona State University
- primary #8C1D40, secondary #FFC627
- source: https://brandguide.asu.edu/brand-elements/design/color
- derivation: hex given (ASU Maroon; ASU Gold)
- contrast on primary: white 8.88, #10131A 2.09; AA text (4.5:1): white

### baylor.edu : Baylor University
- primary #154734, secondary #FFB81C
- source: https://brand.web.baylor.edu/brand-standards/official-brand-colors
- derivation: hex given (Baylor Green PMS 3435; University Gold PMS 1235)
- contrast on primary: white 10.59, #10131A 1.75; AA text (4.5:1): white

### uc.edu : University of Cincinnati
- primary #E00122, secondary #000000
- source: https://www.uc.edu/about/marketing-communications/brand-guide/visual-identity/color.html
- derivation: hex given (UC Red; Black)
- contrast on primary: white 5.00, #10131A 3.71; AA text (4.5:1): white

### colorado.edu : University of Colorado at Boulder
- primary #CFB87C, secondary #000000
- source: https://www.colorado.edu/imc/cu-boulder-brand/visual-identity
- derivation: hex given (CU Gold PMS 4525 C; black from https://www.colorado.edu/digital-accessibility/color-combinations)
- contrast on primary: white 1.94, #10131A 9.56; AA text (4.5:1): #10131A
- note: Gold is light; CU also defines a darker text gold #8D7334 for apparel.

### uh.edu : University of Houston
- primary #C8102E, secondary null
- source: https://www.uh.edu/brand/brand-identity/style-guide/index.php
- derivation: hex given (Red PMS 186 C; White)
- contrast on primary: white 5.88, #10131A 3.16; AA text (4.5:1): white

### iastate.edu : Iowa State University
- primary #C8102E, secondary #F1BE48
- source: https://www.brandmarketing.iastate.edu/brand-elements/color-palette/
- derivation: hex given (Cardinal PMS 186C; Gold PMS 142C)
- contrast on primary: white 5.88, #10131A 3.16; AA text (4.5:1): white
- note: A 2025 trademark fundraising guide gives #C91235 for cardinal; brand standards site used.

### ku.edu : University of Kansas
- primary #0051BA, secondary #E8000D
- source: https://brand.ku.edu/guidelines/design/color
- derivation: hex given (Kansas Blue PMS 293; Crimson PMS 186)
- contrast on primary: white 7.28, #10131A 2.55; AA text (4.5:1): white

### k-state.edu : Kansas State University
- primary #512888, secondary null
- source: https://www.k-state.edu/communications-marketing/brand-style/visual-language/color/
- derivation: hex given (Royal Purple PMS 268+)
- contrast on primary: white 10.45, #10131A 1.78; AA text (4.5:1): white

### okstate.edu : Oklahoma State University
- primary #FE5C00, secondary #000000
- source: https://brand.okstate.edu/branding-guidelines/colors
- derivation: hex given (Orange PMS 021; Black)
- contrast on primary: white 3.11, #10131A 5.97; AA text (4.5:1): #10131A

### tcu.edu : Texas Christian University
- primary #4D1979, secondary #A3A9AC
- source: https://brand.tcu.edu/university-color/
- derivation: hex given (Horned Frog Purple PMS 268 C; Horned Frog Grey from https://brand.tcu.edu/paint-box/)
- contrast on primary: white 12.13, #10131A 1.53; AA text (4.5:1): white; FLAG: very dark

### ttu.edu : Texas Tech University
- primary #E90802, secondary #000000
- source: https://www.ttu.edu/brand/visual-identity/index.php
- derivation: hex given (Scarlet PMS 485 C; Black)
- contrast on primary: white 4.67, #10131A 3.98; AA text (4.5:1): white
- note: TTU says its red is a special ink mix; the hex is an approximation.

### ucf.edu : University of Central Florida
- primary #EDB80D, secondary #000000
- source: https://www.ucf.edu/brand/brand-assets/colors/
- derivation: hex given (Bold Gold PMS 7406; Black)
- contrast on primary: white 1.83, #10131A 10.14; AA text (4.5:1): #10131A
- note: A UCF unit guide shows an older gold #FFC904.

### utah.edu : University of Utah
- primary #BE0000, secondary null
- source: https://brand.utah.edu/branding/colors/
- derivation: hex given (Utah Red, digital)
- contrast on primary: white 6.58, #10131A 2.82; AA text (4.5:1): white

### wvu.edu : West Virginia University
- primary #EAAA00, secondary #002855
- source: https://trademarklicensing.wvu.edu/protected-indicia/brand-guide
- derivation: hex given (Gold PMS 124 C; Blue PMS 295 C)
- contrast on primary: white 2.05, #10131A 9.07; AA text (4.5:1): #10131A
- note: scm.wvu.edu lists web gold #EEAA00; trademark and alumni guides say #EAAA00.

### oregonstate.edu : Oregon State University
- primary #D73F09, secondary null
- source: https://communications.oregonstate.edu/brand-guide/colors
- derivation: hex given (Beaver Orange, PMS 1665)
- contrast on primary: white 4.56, #10131A 4.07; AA text (4.5:1): white

### wsu.edu : Washington State University
- primary #A60F2D, secondary #4D4D4D
- source: https://brand.wsu.edu/colors/
- derivation: hex given (Crimson PMS 201 C; Gray PMS 7540 C)
- contrast on primary: white 7.70, #10131A 2.41; AA text (4.5:1): white
- note: Older WSU guides use #981E32 and #5E6A71.

### stanford.edu : Stanford University
- primary #8C1515, secondary null
- source: https://identity.stanford.edu/design-elements/color/primary-colors/
- derivation: hex given (Cardinal red PMS 201 C)
- contrast on primary: white 9.40, #10131A 1.98; AA text (4.5:1): white

### berkeley.edu : University of California, Berkeley
- primary #002676, secondary #FDB515
- source: https://brand.berkeley.edu/visual-identity/colors/
- derivation: hex given (Berkeley Blue; California Gold)
- contrast on primary: white 13.65, #10131A 1.36; AA text (4.5:1): white; FLAG: very dark
- note: CONFLICT: other Berkeley sites (campaign toolkit, alumni) list Berkeley Blue #003262. The newer brand site (brightened blue) is used.

### boisestate.edu : Boise State University
- primary #0033A0, secondary #D64309
- source: https://www.boisestate.edu/brand/visual-identity/colors/
- derivation: hex given (PMS 286 C blue; PMS 172 C orange)
- contrast on primary: white 10.60, #10131A 1.75; AA text (4.5:1): white

### colostate.edu : Colorado State University
- primary #1E4D2B, secondary #C8C372
- source: https://brand.colostate.edu/color/
- derivation: hex given (CSU Green PMS 357; CSU Gold)
- contrast on primary: white 9.76, #10131A 1.90; AA text (4.5:1): white
- note: Green is dark; gold is muted.

### unlv.edu : University of Nevada, Las Vegas
- primary #B10202, secondary #666666
- source: https://www.unlv.edu/brand/colors
- derivation: hex given for screen (Scarlet; Gray)
- contrast on primary: white 7.29, #10131A 2.55; AA text (4.5:1): white
- note: Print scarlet is #E31837; screen values used.

### unm.edu : University of New Mexico
- primary #BA0C2F, secondary #A7A8AA
- source: https://brand.unm.edu/brand-style/color-palette/index.html
- derivation: hex given (Cherry PMS 200 C; Silver Cool Gray 6 C)
- contrast on primary: white 6.60, #10131A 2.82; AA text (4.5:1): white

### uwyo.edu : University of Wyoming
- primary #492F24, secondary #FFC425
- source: https://www.uwyo.edu/web/branding/index.html
- derivation: hex given (UW Brown; UW Gold) in the web branding guide
- contrast on primary: white 12.24, #10131A 1.52; AA text (4.5:1): white; FLAG: very dark
- note: Brown is very dark; gold may suit the theme better.

### usu.edu : Utah State University
- primary #0F2439, secondary null
- source: https://www.usu.edu/brand/toolkit/guides/colors
- derivation: hex given (Aggie Blue, dominant colour)
- contrast on primary: white 15.77, #10131A 1.18; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Athletics guide uses #00263A. Very dark.

### temple.edu : Temple University
- primary #A41E35, secondary null
- source: https://cph.temple.edu/sites/cph/files/images/Logos/Temple%20University%20Color%20Palette.pdf
- derivation: hex given in the Temple University color palette PDF (Cherry PMS 201C)
- contrast on primary: white 7.46, #10131A 2.49; AA text (4.5:1): white
- note: Older 2014 guide: #9E1B34.

### fiu.edu : Florida International University
- primary #081E3F, secondary #D1A644
- source: https://brand.fiu.edu/visual-styles/colors/
- derivation: hex given (FIU Blue; FIU Gold)
- contrast on primary: white 16.56, #10131A 1.12; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Gold differs by FIU site: the Pantera design system uses #B6862C. Blue is near-black.

### usf.edu : University of South Florida
- primary #006747, secondary #CFC493
- source: https://www.usf.edu/ucm/marketing/colors.aspx
- derivation: hex given (USF Green PMS 342; USF Gold PMS 4535)
- contrast on primary: white 6.93, #10131A 2.68; AA text (4.5:1): white

### nyu.edu : New York University
- primary #57068C, secondary null
- source: https://www.nyu.edu/employees/resources-and-services/media-and-communications/nyu-brand-guidelines/designing-in-our-style/nyu-colors.html
- derivation: hex given (NYU Violet PMS 2597 C)
- contrast on primary: white 11.60, #10131A 1.60; AA text (4.5:1): white

### bu.edu : Boston University
- primary #CC0000, secondary null
- source: https://www.bu.edu/devcom/files/2010/04/BUBrand_Guidelines_book.pdf
- derivation: hex given as the web hex in the BU Brand Identity Standards (2008 edition, red)
- contrast on primary: white 5.89, #10131A 3.16; AA text (4.5:1): white
- note: OLDER SOURCE (2008); newer BU guides were not readable. Official colours: scarlet and white. Medium confidence.

### northeastern.edu : Northeastern University
- primary #C8102E, secondary null
- source: https://brand.northeastern.edu/design-and-experiences/color/
- derivation: hex given (Northeastern red, PMS 186)
- contrast on primary: white 5.88, #10131A 3.16; AA text (4.5:1): white

### cornell.edu : Cornell University
- primary #B31B1B, secondary null
- source: https://brand.cornell.edu/design-center/colors/
- derivation: hex given (Carnelian, PMS 187)
- contrast on primary: white 6.80, #10131A 2.73; AA text (4.5:1): white

### upenn.edu : University of Pennsylvania
- primary #011F5B, secondary #990000
- source: https://branding.web-resources.upenn.edu/logos-and-branding/elements-penn-logo
- derivation: hex given (Penn Blue PMS 288; Penn Red PMS 201)
- contrast on primary: white 15.57, #10131A 1.19; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Blue is very dark.

### harvard.edu : Harvard University
- primary #A51C30, secondary null
- source: https://www.harvard.edu/guidelines/wp-content/uploads/sites/10/2025/12/2025_11_24_Harvard_Graphic_Identity_Guidelines-1.pdf
- derivation: hex given (Harvard Crimson, PMS 187)
- contrast on primary: white 7.48, #10131A 2.49; AA text (4.5:1): white

### mit.edu : Massachusetts Institute of Technology
- primary #750014, secondary null
- source: https://brand.mit.edu/color
- derivation: hex given (MIT Red, PMS 202 C)
- contrast on primary: white 11.89, #10131A 1.56; AA text (4.5:1): white; FLAG: very dark
- note: Very dark.

### jhu.edu : Johns Hopkins University
- primary #002D72, secondary #F1C400
- source: https://brand.jhu.edu/visual-identity/enterprise-branding/
- derivation: hex given (Heritage Blue PMS 288 C; Gold accent)
- contrast on primary: white 12.98, #10131A 1.43; AA text (4.5:1): white; FLAG: very dark
- note: Heritage Blue is dark; it was #0057AC before 2020.

### georgetown.edu : Georgetown University
- primary #041E42, secondary #63666A
- source: https://www.georgetown.edu/color-guide/
- derivation: hex given (Georgetown Blue; Georgetown Gray, Cool Gray 10)
- contrast on primary: white 16.54, #10131A 1.12; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Blue is near-black.

### rice.edu : Rice University
- primary #00205B, secondary #7C7E7F
- source: https://brand.rice.edu/colors
- derivation: hex given (Rice Blue; Rice Gray)
- contrast on primary: white 15.47, #10131A 1.20; AA text (4.5:1): white; FLAG: NEAR-BLACK

### tulane.edu : Tulane University
- primary #285C4D, secondary #71C5E8
- source: https://communications.tulane.edu/brand/color
- derivation: hex given (Tulane Green PMS 626; Tulane Blue PMS 297)
- contrast on primary: white 7.70, #10131A 2.41; AA text (4.5:1): white
- note: Core Colors page lists a web green #336666.

### emory.edu : Emory University
- primary #012169, secondary #B58500
- source: https://brand.emory.edu/color.html
- derivation: hex given (Emory Blue PMS 280; Gold PMS 125)
- contrast on primary: white 14.76, #10131A 1.26; AA text (4.5:1): white; FLAG: very dark
- note: Other Emory pages use a PMS 294 blue (#002F6C).

### yale.edu : Yale University
- primary #00356B, secondary null
- source: https://licensing.yale.edu/sites/default/files/files/Yale_Brand_Guidelines_2022.pdf
- derivation: hex given (Yale Blue)
- contrast on primary: white 12.20, #10131A 1.52; AA text (4.5:1): white; FLAG: very dark
- note: Some Yale sites vary (#003D76, #0F4D92); #00356B used in identity guidelines.

### princeton.edu : Princeton University
- primary #E77500, secondary null
- source: https://oitstyleguide.princeton.edu/brand-and-marketing-guidelines/color-palette
- derivation: hex given in the Princeton OIT style guide (Orange)
- contrast on primary: white 3.02, #10131A 6.14; AA text (4.5:1): #10131A
- note: Other Princeton sources use #EE7F2D or #F58025; unit-level guide, medium confidence.

### brown.edu : Brown University
- primary #4E3629, secondary #C00404
- source: https://engineering.brown.edu/resources/communications-creative-resources/logo-visual-identity
- derivation: hex given in the Brown School of Engineering identity page (Brown; Red)
- contrast on primary: white 11.15, #10131A 1.67; AA text (4.5:1): white
- note: Unit-level page; the central visual identity page lists no hex. Brown is very dark, red may suit the theme better.

### columbia.edu : Columbia University
- primary #B9D9EB, secondary null
- source: https://visualidentity.columbia.edu/content/color
- derivation: hex given (Columbia Blue, PMS 290 C)
- contrast on primary: white 1.48, #10131A 12.55; AA text (4.5:1): #10131A
- note: Very light; white text fails badly.

## Unverified (skipped)

- troy.edu (Troy University): Cardinal, Silver and Black named on helpdesk.troy.edu; the brand page (troy.edu/about-us/offices-departments/office-marketing-communication/all-ways-real-always-troy.html) shows hex only inside images; third-party sites disagree (#8B2232 vs #6D0017). Official PMS 202 cardinal is mentioned in Troy policy.
- jsu.edu (Jacksonville State University): Brand guide is an issuu flipbook (isu.pub/V7b0ZTo) that could not be read; only 'red and white' confirmed.
- bsc.edu (Birmingham-Southern College): Only Pantone (Gold 130, Blue 286) on an athletics policy page; the college closed in 2024.
- montevallo.edu (University of Montevallo): Not in the Hipo registry copy (no domain to key on); not researched.
- bc.edu (Boston College): Only Pantone for athletics inks (202, 4515); no hex on an official page found.
- umass.edu (University of Massachusetts Amherst): Official pages conflict: #840028 (brand colors page) vs #881C1C (brand elements page).
- byu.edu (Brigham Young University): Royal blue hex conflicts across official BYU pages (#0047BA, #0062B8, #003DA5); navy hex not obtained.
- sdsu.edu (San Diego State University): Black confirmed (#000000) but the red hex was not retrieved from brand.sdsu.edu.

---

# Addendum 2026-10-17 (second pass): 149 more schools

Same rules and checks as above. Data file now has %d domains. Each value was read through a search summary restricted to the school's own domain (allowed_domains = the school's domain), so every source is an official school page or PDF; no third-party colour site was used. Re-open the source URL before treating a single value as final. Rows marked WEAKER in the note rely on an older document, a unit-level page, or a PDF whose text extraction was inconsistent. Where official pages disagree, the value from the newest or most central page was stored and the conflict is in the note.

Previously unverified schools now resolved in this pass: sdsu.edu (red from brand.sdsu.edu) and byu.edu (navy only). umass.edu and bc.edu remain unverified.

## Second pass: flagged primaries (human decision needed)

- ucsd.edu (University of California, San Diego) #182B49: very dark (white 14.18, #10131A 1.31)
- ucdavis.edu (University of California, Davis) #022851: very dark (white 14.74, #10131A 1.26)
- ucsb.edu (University of California, Santa Barbara) #003660: very dark (white 12.38, #10131A 1.50)
- fullerton.edu (California State University, Fullerton) #00244E: NEAR-BLACK (white 15.41, #10131A 1.21)
- txstate.edu (Texas State University) #501214: very dark (white 14.61, #10131A 1.27)
- georgiasouthern.edu (Georgia Southern University) #001344: NEAR-BLACK (white 17.85, #10131A 1.04)
- augusta.edu (Augusta University) #002F55: very dark (white 13.66, #10131A 1.36)
- fau.edu (Florida Atlantic University) #003366: very dark (white 12.61, #10131A 1.47)
- unf.edu (University of North Florida) #0A233F: NEAR-BLACK (white 15.85, #10131A 1.17)
- uwf.edu (University of West Florida) #00205B: NEAR-BLACK (white 15.47, #10131A 1.20)
- etsu.edu (East Tennessee State University) #00053E: NEAR-BLACK (white 19.24, #10131A 1.04)
- utc.edu (University of Tennessee at Chattanooga) #112E51: very dark (white 13.69, #10131A 1.36)
- latech.edu (Louisiana Tech University) #003087: very dark (white 11.85, #10131A 1.57)
- uno.edu (University of New Orleans) #003366: very dark (white 12.61, #10131A 1.47)
- utm.edu (University of Tennessee, Martin) #0B2341: NEAR-BLACK (white 15.78, #10131A 1.18)
- fit.edu (Florida Institute of Technology) #770000: very dark (white 11.77, #10131A 1.58)
- gwu.edu (George Washington University) #033C5A: very dark (white 11.68, #10131A 1.59)
- luc.edu (Loyola University Chicago) #5A0722: very dark (white 14.11, #10131A 1.32)
- siu.edu (Southern Illinois University-Carbondale) #6C0633: very dark (white 12.27, #10131A 1.51)
- cmich.edu (Central Michigan University) #6A0032: very dark (white 12.66, #10131A 1.47)
- uakron.edu (University of Akron) #070C72: NEAR-BLACK (white 16.10, #10131A 1.15)
- udayton.edu (University of Dayton) #003087: very dark (white 11.85, #10131A 1.57)
- albany.edu (State University of New York at Albany) #46166B: very dark (white 13.23, #10131A 1.40)
- rochester.edu (University of Rochester) #001E5F: NEAR-BLACK (white 15.54, #10131A 1.20)
- drexel.edu (Drexel University) #07294D: very dark (white 14.65, #10131A 1.27)
- villanova.edu (Villanova University) #002664: very dark (white 14.37, #10131A 1.29)
- lehigh.edu (Lehigh University) #502D0E: very dark (white 12.19, #10131A 1.52)
- odu.edu (Old Dominion University) #043657: very dark (white 12.57, #10131A 1.48)
- jmu.edu (James Madison University) #450084: very dark (white 13.24, #10131A 1.40)
- uncg.edu (The University of North Carolina at Greensboro) #0F2044: NEAR-BLACK (white 16.03, #10131A 1.16)
- winthrop.edu (Winthrop University) #6B0D0E: very dark (white 12.43, #10131A 1.49)
- byu.edu (Brigham Young University) #002E5D: very dark (white 13.56, #10131A 1.37)
- weber.edu (Weber State University) #492365: very dark (white 12.27, #10131A 1.51)
- wichita.edu (Wichita State University) #FFDB00: NEAR-WHITE (white 1.37, #10131A 13.61)
- montana.edu (Montana State University - Bozeman) #162960: very dark (white 13.81, #10131A 1.35)
- umt.edu (University of Montana) #70002E: very dark (white 12.15, #10131A 1.53)
- unr.edu (University of Nevada, Reno) #041E42: NEAR-BLACK (white 16.54, #10131A 1.12)
- mines.edu (Colorado School of Mines) #21314D: very dark (white 13.03, #10131A 1.43)
- howard.edu (Howard University) #003A63: very dark (white 11.76, #10131A 1.58)
- uconn.edu (University of Connecticut) #000E2F: NEAR-BLACK (white 19.02, #10131A 1.02)
- umaine.edu (University of Maine) #082E58: very dark (white 13.62, #10131A 1.36)
- pepperdine.edu (Pepperdine University) #1E2859: very dark (white 13.97, #10131A 1.33)
- ucsf.edu (University of California, San Francisco) #052049: NEAR-BLACK (white 16.04, #10131A 1.16)
- acu.edu (Abilene Christian University) #4F2170: very dark (white 11.77, #10131A 1.58)
- butler.edu (Butler University) #13294B: very dark (white 14.52, #10131A 1.28)
- mc.edu (Mississippi College) #0C2340: NEAR-BLACK (white 15.79, #10131A 1.18)
- columbusstate.edu (Columbus State University) #003359: very dark (white 12.98, #10131A 1.43)
- austincc.edu (Austin Community College) #4D1979: very dark (white 12.13, #10131A 1.53)
- lonestar.edu (Lone Star College System) #003768: very dark (white 12.02, #10131A 1.55)

## Second pass: primaries where neither white nor #10131A reaches 4.5:1


## Second pass: verified schools (149)

### ucsd.edu : University of California, San Diego
- primary #182B49, secondary #C69214
- source: https://brand.ucsd.edu/visual-brand/color/index.html
- derivation: hex given (Navy PMS 2767; Gold PMS 1245)
- contrast on primary: white 14.18, #10131A 1.31; AA text (4.5:1): white; FLAG: very dark
- note: Palette also lists UC San Diego Blue #00629B and Yellow #FFCD00.

### uci.edu : University of California, Irvine
- primary #255799, secondary #FECC07
- source: https://brand.uci.edu/identity/colors.php
- derivation: hex given (UCI Blue; UCI Gold)
- contrast on primary: white 7.24, #10131A 2.57; AA text (4.5:1): white
- note: Engineering school uses a different web blue/gold; UCI announced new brand standards June 2024, re-check.

### ucdavis.edu : University of California, Davis
- primary #022851, secondary #FFBF00
- source: https://ftmba.ucdavis.edu/post/colors
- derivation: hex given (Aggie Blue; Aggie Gold PMS 110 C); unit-level page on ucdavis.edu quoting the UC Davis brand guide (https://communicationsguide.ucdavis.edu/brand-guide)
- contrast on primary: white 14.74, #10131A 1.26; AA text (4.5:1): white; FLAG: very dark
- note: Hex read from a UC Davis unit page, not the central guide table.

### ucsb.edu : University of California, Santa Barbara
- primary #003660, secondary #FEBC11
- source: https://brand.ucsb.edu/visual-identity/color
- derivation: hex given (Navy; Gold)
- contrast on primary: white 12.38, #10131A 1.50; AA text (4.5:1): white; FLAG: very dark
- note: Coral #EF5645 is an accent.

### ucr.edu : University of California, Riverside
- primary #003DA5, secondary #FFB81C
- source: https://brand.ucr.edu/ucr-colors-old
- derivation: hex given (UCR Blue PMS 293C; Gold PMS 1235C)
- contrast on primary: white 9.50, #10131A 1.96; AA text (4.5:1): white
- note: URL path says 'old'; same palette appears in 2020 style guide PDF.

### ucsc.edu : University of California, Santa Cruz
- primary #003C6C, secondary #FDC700
- source: https://communications.ucsc.edu/brand-overview/color/
- derivation: hex given (Blue; Yellow)
- contrast on primary: white 11.27, #10131A 1.65; AA text (4.5:1): white

### sdsu.edu : San Diego State University
- primary #D41736, secondary #A6192E
- source: https://brand.sdsu.edu/identity/design-elements/colors
- derivation: hex given (bright red; dark red; also charcoal #2D2828)
- contrast on primary: white 5.28, #10131A 3.52; AA text (4.5:1): white
- note: Dark red #A6192E is reserved for web links.

### sjsu.edu : San Jose State University
- primary #0055A2, secondary #E5A823
- source: https://www.sjsu.edu/communications/brand/visual-style/color/web.php
- derivation: hex given (SJSU Blue; SJSU Gold)
- contrast on primary: white 7.44, #10131A 2.50; AA text (4.5:1): white

### csun.edu : California State University, Northridge
- primary #D00D2D, secondary #000000
- source: https://www.csun.edu/sites/default/files/01_CSUN%20Identity%20Guidelines_0.pdf
- derivation: hex given (red PMS 186; black)
- contrast on primary: white 5.56, #10131A 3.34; AA text (4.5:1): white
- note: CONFLICT: athletics guide uses red #CE1126.

### fullerton.edu : California State University, Fullerton
- primary #00244E, secondary #FF7900
- source: https://brand.fullerton.edu/colors/
- derivation: hex given (Titan Blue; Titan Orange)
- contrast on primary: white 15.41, #10131A 1.21; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Athletics guide uses #00263A/#FF671F.

### unt.edu : University of North Texas
- primary #00853E, secondary null
- source: https://identityguide.unt.edu/create-our-look/color
- derivation: hex given (UNT Green PMS 349-family, official green)
- contrast on primary: white 4.75, #10131A 3.92; AA text (4.5:1): white

### utsa.edu : The University of Texas at San Antonio
- primary #F15A22, secondary #032044
- source: https://www.utsa.edu/marcomstudio/resources/style-guides/brand-guidelines/color.html
- derivation: hex given (UTSA Orange PMS 1665; Midnight PMS 289)
- contrast on primary: white 3.37, #10131A 5.51; AA text (4.5:1): #10131A
- note: Accessible text orange D3430D is also approved; Midnight is near-black.

### utdallas.edu : University of Texas at Dallas
- primary #154734, secondary #E87500
- source: https://brand.utdallas.edu/graphics-visual-identity/color-palette/
- derivation: hex given (UTD Green; UTD Orange PMS 158)
- contrast on primary: white 10.59, #10131A 1.75; AA text (4.5:1): white
- note: Development office page lists green #053D2C; central brand standards used.

### uta.edu : University of Texas at Arlington
- primary #0064B1, secondary #F58025
- source: https://www.uta.edu/administration/mme/brand-standards/logo-design-identity/color-standards
- derivation: hex given (UTA Blue PMS 293; UTA Orange PMS 158)
- contrast on primary: white 6.07, #10131A 3.06; AA text (4.5:1): white
- note: Web-only blue #003865 and web text orange #C45517 also exist; orange is not accessible for text.

### utrgv.edu : The University of Texas at Rio Grande Valley
- primary #CB4900, secondary #646469
- source: https://www.utrgv.edu/brand/identity/color-palette/index.htm
- derivation: hex given on web palette (orange; gray)
- contrast on primary: white 4.67, #10131A 3.98; AA text (4.5:1): white
- note: CONFLICT: style guide PDF lists orange #F05023.

### txstate.edu : Texas State University
- primary #501214, secondary #AC9155
- source: https://brand.txstate.edu/assets/colors.html
- derivation: hex given (Texas State Maroon; Dark Gold)
- contrast on primary: white 14.61, #10131A 1.27; AA text (4.5:1): white; FLAG: very dark

### smu.edu : Southern Methodist University
- primary #354CA1, secondary #CC0035
- source: https://www.smu.edu/brand/color-palette
- derivation: hex given on-screen (blue; red)
- contrast on primary: white 7.78, #10131A 2.39; AA text (4.5:1): white
- note: Perkins school guide uses #0033A0/#C8102E.

### gsu.edu : Georgia State University
- primary #0039A6, secondary #CC0000
- source: https://commkit.gsu.edu/website-management/web-color-guidelines/
- derivation: hex given (Georgia State Blue PMS 286; athletics red PMS 186)
- contrast on primary: white 9.83, #10131A 1.89; AA text (4.5:1): white

### kennesaw.edu : Kennesaw State University
- primary #FFC629, secondary #000000
- source: https://campus.kennesaw.edu/offices-services/stratcomm/branding/logo-color-guidelines/color-guidelines.php
- derivation: hex given (KSU Gold PMS 123C; black)
- contrast on primary: white 1.57, #10131A 11.82; AA text (4.5:1): #10131A
- note: Athletics guide gold is #FDBB30.

### georgiasouthern.edu : Georgia Southern University
- primary #001344, secondary #9A8348
- source: https://www.georgiasouthern.edu/offices/communications-marketing/wordpress/guidelines/web-colors-fonts
- derivation: hex given (GS Navy; Logo Gold)
- contrast on primary: white 17.85, #10131A 1.04; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: 2018 guide listed #041E42/#A99260; current web guide used.

### augusta.edu : Augusta University
- primary #002F55, secondary #A5ACAF
- source: https://brand.augusta.edu/color/
- derivation: hex given (Augusta Blue; Augusta Grey)
- contrast on primary: white 13.66, #10131A 1.36; AA text (4.5:1): white; FLAG: very dark
- note: Athletic Blue #00AEEF is for athletics only.

### ung.edu : University of North Georgia
- primary #1F3D7C, secondary #FFC62F
- source: https://ung.edu/strategic-communications-marketing/branding/visual-identity-assets.php
- derivation: hex given (UNG Blue/Royal PMS 287C; UNG Gold PMS 123C)
- contrast on primary: white 10.41, #10131A 1.78; AA text (4.5:1): white

### fau.edu : Florida Atlantic University
- primary #003366, secondary #CC0000
- source: https://www.fau.edu/styleguide/colors/
- derivation: hex given (FAU Blue PMS 295; FAU Red)
- contrast on primary: white 12.61, #10131A 1.47; AA text (4.5:1): white; FLAG: very dark
- note: Red is meant as complement, never dominant.

### unf.edu : University of North Florida
- primary #0A233F, secondary #A7A8A9
- source: https://www.unf.edu/brand/colors.html
- derivation: hex given (Osprey Blue; Osprey Gray)
- contrast on primary: white 15.85, #10131A 1.17; AA text (4.5:1): white; FLAG: NEAR-BLACK

### uwf.edu : University of West Florida
- primary #00205B, secondary #00A346
- source: https://uwf.edu/brand/color/
- derivation: hex given (Argo Navy; Argo Green, 2026 refresh)
- contrast on primary: white 15.47, #10131A 1.20; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: CONFLICT: older UWF page lists blue #004C97 and green #007A33; the refreshed palette is used.

### nova.edu : Nova Southeastern University
- primary #003893, secondary null
- source: https://www.nova.edu/brand/colors.html
- derivation: hex given on web palette (NSU Blue)
- contrast on primary: white 10.57, #10131A 1.76; AA text (4.5:1): white
- note: Print blue is #002A84 (PMS 287); web value used.

### sfasu.edu : Stephen F. Austin State University
- primary #5F259F, secondary null
- source: https://www.sfasu.edu/umc/brand-toolkit
- derivation: hex given (SFA Purple PMS 267 C, RGB 95-37-159)
- contrast on primary: white 9.33, #10131A 1.99; AA text (4.5:1): white
- note: Toolkit also shows #660099 for the same purple.

### usm.edu : University of Southern Mississippi
- primary #FFAB00, secondary #000000
- source: https://www.usm.edu/university-communications/files/usm_graphic_standards_september2020.pdf
- derivation: hex given in 2020 graphic standards (Gold PMS 123 C; Black)
- contrast on primary: white 1.90, #10131A 9.80; AA text (4.5:1): #10131A
- note: WEAKER: older PDF; it lists gold as '#FFAB00 or #FFD046'.

### mtsu.edu : Middle Tennessee State University
- primary #007BC3, secondary #004776
- source: https://www.mtsu.edu/web-training/fonts/
- derivation: hex given on the MTSU web branding page (True Blue PMS 300; Raider Navy PMS 648)
- contrast on primary: white 4.54, #10131A 4.09; AA text (4.5:1): white
- note: CONFLICT: 2021 style guide PDF lists blue #0066CC.

### tnstate.edu : Tennessee State University
- primary #00539F, secondary null
- source: https://www.tnstate.edu/publications/documents/styleguide.pdf
- derivation: hex given (TSU Blue / Reflex Blue)
- contrast on primary: white 7.67, #10131A 2.42; AA text (4.5:1): white
- note: CONFLICT: logo page lists blue #0070C0 and red #8C0000.

### etsu.edu : East Tennessee State University
- primary #00053E, secondary #FFC72C
- source: https://www.etsu.edu/brand/design.php
- derivation: hex given (ETSU Blue PMS 282; ETSU Gold PMS 123)
- contrast on primary: white 19.24, #10131A 1.04; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Blue is near-black.

### tntech.edu : Tennessee Technological University
- primary #753BBD, secondary #FFD100
- source: https://www.tntech.edu/ocm/color.php
- derivation: hex given (purple PMS 266C; gold PMS 109C)
- contrast on primary: white 6.74, #10131A 2.76; AA text (4.5:1): white
- note: Older page version listed purple #582C83.

### utc.edu : University of Tennessee at Chattanooga
- primary #112E51, secondary #FDB736
- source: https://www.utc.edu/sites/default/files/2022-01/UTC-Color-Reference.pdf
- derivation: hex given (Blue PMS 295; Gold PMS 124)
- contrast on primary: white 13.69, #10131A 1.36; AA text (4.5:1): white; FLAG: very dark
- note: Web colors page shows blue RGB 0/56/107 (inconsistent with its own hex); PDF used.

### apsu.edu : Austin Peay State University
- primary #C41E3A, secondary #000000
- source: https://www.apsu.edu/identity/colors.php
- derivation: hex given (Pantone 200 Red; black)
- contrast on primary: white 5.84, #10131A 3.18; AA text (4.5:1): white
- note: Brand PDF lists different RGB for the red.

### louisiana.edu : University of Louisiana at Lafeyette
- primary #CE181E, secondary null
- source: https://louisiana.edu/web/tutorials-resources/web-style-guide/approved-web-colors
- derivation: hex given (Primary Red for the new web system)
- contrast on primary: white 5.56, #10131A 3.34; AA text (4.5:1): white
- note: Older CMS colour was #A00B0B.

### latech.edu : Louisiana Tech University
- primary #003087, secondary #CB333B
- source: https://brand.latech.edu/identity-standards/university-colors/
- derivation: hex given (Tech Blue PMS 287; Tech Red PMS 1797)
- contrast on primary: white 11.85, #10131A 1.57; AA text (4.5:1): white; FLAG: very dark

### uno.edu : University of New Orleans
- primary #003366, secondary #666666
- source: https://www.uno.edu/strategic-marketing/identity-standards
- derivation: hex given (UNO Blue PMS 540; Silver)
- contrast on primary: white 12.61, #10131A 1.47; AA text (4.5:1): white; FLAG: very dark
- note: Hex are approximations printed in the identity standards.

### ulm.edu : University of Louisiana at Monroe
- primary #840029, secondary #FDB913
- source: https://www.ulm.edu/pharmacy/documents/ospa/studentdresscode.pdf
- derivation: hex given in a ULM document (Maroon PMS 202 C; Heritage Gold PMS 124 C)
- contrast on primary: white 10.43, #10131A 1.78; AA text (4.5:1): white
- note: WEAKER: unit-level ULM document; 2025-26 brand guide PDF not read.

### mcneese.edu : McNeese State University
- primary #00477F, secondary #FFD520
- source: https://www.mcneese.edu/wp-content/uploads/2023/04/McNeese-Branding-Overview-7.24.pdf
- derivation: hex given (Official Blue, listed with PMS 287 C; Official Gold PMS 116 C)
- contrast on primary: white 9.51, #10131A 1.95; AA text (4.5:1): white
- note: WEAKER: 2023 PDF; its blue hex #00477F does not match its own RGB 0/48/135 (#003087).

### mercer.edu : Mercer University
- primary #F76800, secondary #222222
- source: https://www.mercer.edu/university-branding/typography-and-colors/
- derivation: hex given (Mercer Orange PMS 716 C; black #222222)
- contrast on primary: white 3.03, #10131A 6.14; AA text (4.5:1): #10131A

### utm.edu : University of Tennessee, Martin
- primary #0B2341, secondary #FF8200
- source: https://www.utm.edu/offices-and-services/office-of-university-relations/_media/UR_StyleGuide_24-1.pdf
- derivation: hex given (PMS 289 blue; PMS 151 orange)
- contrast on primary: white 15.78, #10131A 1.18; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Blue is near-black.

### rhodes.edu : Rhodes College
- primary #C4022B, secondary #000000
- source: https://www.rhodes.edu/sites/default/files/RHODES_Brand_Standards_2020.pdf
- derivation: hex given in the 2020 brand standards (Rhodes Red PMS 186 C; Rhodes Black)
- contrast on primary: white 6.19, #10131A 3.00; AA text (4.5:1): white
- note: WEAKER: 2020 edition; the 2025 edition was not read for the red hex.

### fit.edu : Florida Institute of Technology
- primary #770000, secondary #AB946C
- source: https://www.fit.edu/marketing-and-communications/marcomm-toolbox/graphic-identity-standards/color-palette-and-typography/
- derivation: hex given (Crimson PMS 202C; Gold PMS 871U)
- contrast on primary: white 11.77, #10131A 1.58; AA text (4.5:1): white; FLAG: very dark
- note: Gold fails contrast on white (2.92 per the school).

### gwu.edu : George Washington University
- primary #033C5A, secondary #AA9868
- source: https://communications.gwu.edu/visual-identity/color-palette
- derivation: hex given (GW Blue PMS 302 web value; Buff PMS 7503)
- contrast on primary: white 11.68, #10131A 1.59; AA text (4.5:1): white; FLAG: very dark
- note: CONFLICT: GW moniker guidelines use blue #002D62; GW says web values are screen-adjusted.

### american.edu : American University
- primary #004FA2, secondary #E0263C
- source: https://www.american.edu/ucm/creative-style-guide.cfm
- derivation: hex given (AU Blue; AU Red)
- contrast on primary: white 7.95, #10131A 2.34; AA text (4.5:1): white
- note: Style guide page is about four years old.

### tufts.edu : Tufts University
- primary #3E8EDE, secondary #63493A
- source: https://brand.tufts.edu/guidelines/color
- derivation: hex given (Tufts Blue PMS 279; Tufts Brown PMS 7519)
- contrast on primary: white 3.43, #10131A 5.42; AA text (4.5:1): #10131A
- note: Palette also has Jumbo Blue #002E6D as a primary.

### uchicago.edu : University of Chicago
- primary #800000, secondary #767676
- source: https://news.uchicago.edu/sites/default/files/UCM_UniversityIdentityGuidelines_2-2020.pdf
- derivation: hex given (Maroon PMS 202; Warm Gray 11 #767676)
- contrast on primary: white 10.95, #10131A 1.70; AA text (4.5:1): white
- note: 2020 identity guide; maroon is very dark.

### depaul.edu : DePaul University
- primary #003DA5, secondary #CE112D
- source: https://resources.depaul.edu/brand/brand-guidelines/colors/Pages/default.aspx
- derivation: hex given (DePaul Blue PMS 293C; red PMS 186C)
- contrast on primary: white 9.50, #10131A 1.96; AA text (4.5:1): white

### luc.edu : Loyola University Chicago
- primary #5A0722, secondary #EAAA00
- source: https://www.luc.edu/umc/brandidentity/brandcomponents/colors/
- derivation: hex given (Loyola Maroon PMS 7421c; Loyola Gold PMS 1235c)
- contrast on primary: white 14.11, #10131A 1.32; AA text (4.5:1): white; FLAG: very dark

### uic.edu : University of Illinois Chicago
- primary #D50032, secondary #001E62
- source: https://brand.uic.edu/visual-identity/color/
- derivation: hex given (Fire Engine Red PMS 199; Navy Pier Blue PMS 2758)
- contrast on primary: white 5.42, #10131A 3.43; AA text (4.5:1): white
- note: UIC web palette uses a different red #CC0000 and blue #2C5581.

### niu.edu : Northern Illinois University
- primary #C8102E, secondary #000000
- source: https://www.niu.edu/communication-standards/visual/colors.shtml
- derivation: hex given (NIU Red PMS 186; black)
- contrast on primary: white 5.88, #10131A 3.16; AA text (4.5:1): white

### siu.edu : Southern Illinois University-Carbondale
- primary #6C0633, secondary #000000
- source: https://ucomm.siu.edu/brand/visuals/colors.php
- derivation: hex given (SIU Maroon PMS 209 web-safe; PMS Black)
- contrast on primary: white 12.27, #10131A 1.51; AA text (4.5:1): white; FLAG: very dark
- note: CONFLICT: older SIU page and web logo standard use #660000.

### wmich.edu : Western Michigan University
- primary #F1C500, secondary #532E1F
- source: https://wmich.edu/marcom/creative/visual-identity/color-guide
- derivation: hex given (Gold PMS 7406; Brown PMS 4625)
- contrast on primary: white 1.65, #10131A 11.26; AA text (4.5:1): #10131A
- note: Older 2013 guide used #EEB111/#331900.

### cmich.edu : Central Michigan University
- primary #6A0032, secondary #FFC82E
- source: https://www.cmich.edu/offices-departments/university-communications/brand-guidelines/visual-language/color-palette
- derivation: hex given (Maroon PMS 209; Gold PMS 123)
- contrast on primary: white 12.66, #10131A 1.47; AA text (4.5:1): white; FLAG: very dark

### wayne.edu : Wayne State University
- primary #0C5449, secondary #FFCC33
- source: https://universityrelations.wayne.edu/docs/identity-style-guide.pdf
- derivation: hex given (Green PMS 561; Gold PMS 1225)
- contrast on primary: white 8.82, #10131A 2.11; AA text (4.5:1): white

### ohio.edu : Ohio University
- primary #00694E, secondary #024230
- source: https://www.ohio.edu/ucm/ohio-brand/colors
- derivation: hex given (Cutler Green; Under the Elms)
- contrast on primary: white 6.71, #10131A 2.77; AA text (4.5:1): white
- note: Page metadata suggests it may be several years old.

### bgsu.edu : Bowling Green State University
- primary #FD5000, secondary #4F2C1D
- source: https://www.bgsu.edu/marketing-and-communications/bgsu-graphic-standards-manual/the-official-identity-colors.html
- derivation: hex given (BGSU Orange PMS 166; BGSU Brown PMS 4625 C)
- contrast on primary: white 3.32, #10131A 5.60; AA text (4.5:1): #10131A
- note: BGSU says hex values are approximations of Pantone.

### uakron.edu : University of Akron
- primary #070C72, secondary #9D9362
- source: https://www.uakron.edu/im/resources/brand/colors
- derivation: hex given on the current brand colours page (Buchtel Blue; Prezi Gold)
- contrast on primary: white 16.10, #10131A 1.15; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: CONFLICT: 2020 refresh PDF used Akron Blue #041E42 / Gold #A89968; blue is very dark.

### miamioh.edu : Miami University of Ohio
- primary #C41230, secondary null
- source: https://miamioh.edu/brand/style/
- derivation: hex given (Miami Red PMS 186C)
- contrast on primary: white 6.04, #10131A 3.08; AA text (4.5:1): white
- note: Brand guide log says Corn Yellow codes changed Sept 2026; only red used.

### udayton.edu : University of Dayton
- primary #003087, secondary #CE0037
- source: https://udayton.edu/brand/colors.php
- derivation: hex given (Flyers Blue PMS 287C; Red Scare PMS 206C, the institutional logo colours)
- contrast on primary: white 11.85, #10131A 1.57; AA text (4.5:1): white; FLAG: very dark
- note: Digital primaries Glow Navy #141B4D and Glow Blue #0200D1 also exist.

### dartmouth.edu : Dartmouth College
- primary #00693E, secondary #12312B
- source: https://communications.dartmouth.edu/guides-and-tools/design-guidelines/dartmouth-colors
- derivation: hex given (Dartmouth Green PMS 349; Forest Green PMS 627)
- contrast on primary: white 6.80, #10131A 2.73; AA text (4.5:1): white

### cmu.edu : Carnegie Mellon University
- primary #C41230, secondary #6D6E71
- source: https://brand.cmu.edu/visual-identity/colors
- derivation: hex given (Carnegie Red PMS 187C; Iron Gray)
- contrast on primary: white 6.04, #10131A 3.08; AA text (4.5:1): white

### rit.edu : Rochester Institute of Technology
- primary #F76902, secondary null
- source: https://www.rit.edu/brandportal/colors
- derivation: hex given (RIT Orange PMS 1505 C, RIT-interpreted RGB)
- contrast on primary: white 3.01, #10131A 6.17; AA text (4.5:1): #10131A
- note: RIT says not to use Pantone's own conversion.

### buffalo.edu : State University of New York at Buffalo
- primary #005BBB, secondary #FFC72C
- source: https://www.buffalo.edu/brand/creative/color/color-palette.html
- derivation: hex given (UB Blue PMS 2935; Solar Strand PMS 123)
- contrast on primary: white 6.53, #10131A 2.84; AA text (4.5:1): white

### stonybrook.edu : State University of New York at Stony Brook
- primary #990000, secondary null
- source: https://www.stonybrook.edu/sbu-brand/design-visual-identity/colors.php
- derivation: hex given (Stony Brook Red PMS 187)
- contrast on primary: white 8.92, #10131A 2.08; AA text (4.5:1): white

### binghamton.edu : State University of New York at Binghamton
- primary #005A43, secondary null
- source: https://www.binghamton.edu/communications-and-marketing/branding/colors.html
- derivation: hex given (Binghamton Green PMS 342)
- contrast on primary: white 8.26, #10131A 2.25; AA text (4.5:1): white
- note: Site RGB values are not consistent across pages; hex used.

### albany.edu : State University of New York at Albany
- primary #46166B, secondary #EEB211
- source: https://www.albany.edu/style-guide/colors
- derivation: hex given (UAlbany Purple PMS 269; Gold PMS 124)
- contrast on primary: white 13.23, #10131A 1.40; AA text (4.5:1): white; FLAG: very dark

### rochester.edu : University of Rochester
- primary #001E5F, secondary #FFD82B
- source: https://brand.rochester.edu/visual-identity/color-system/
- derivation: hex given (URochester Navy PMS 2748 C; Dandelion Yellow)
- contrast on primary: white 15.54, #10131A 1.20; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: 2022 spirit guide used older blue/yellow; refreshed brand used.

### drexel.edu : Drexel University
- primary #07294D, secondary #FFC600
- source: https://drexel.edu/identity/drexel/color
- derivation: hex given (Drexel Blue PMS 294C; Drexel Gold PMS 7548C)
- contrast on primary: white 14.65, #10131A 1.27; AA text (4.5:1): white; FLAG: very dark
- note: Blue is near-black.

### villanova.edu : Villanova University
- primary #002664, secondary #847248
- source: https://www.villanova.edu/university/comm-marketing/guidelines/villanova-visual-identity/university-colors.html
- derivation: hex given (Signature Blue PMS 281; gold metallic PMS 871 screen value)
- contrast on primary: white 14.37, #10131A 1.29; AA text (4.5:1): white; FLAG: very dark

### lehigh.edu : Lehigh University
- primary #502D0E, secondary #FFE41E
- source: https://wms-styleguide.lehigh.edu/components/detail/colors
- derivation: hex given in the Lehigh web design system (Lehigh Brown; Golden Hour accent)
- contrast on primary: white 12.19, #10131A 1.52; AA text (4.5:1): white; FLAG: very dark
- note: WEAKER: web style guide, school colours are brown and white; Pantone not stated.

### gmu.edu : George Mason University
- primary #005239, secondary #FFC733
- source: https://brand.gmu.edu/brand-guide/brand-colors
- derivation: hex given (George Mason Green PMS 357C; Gold PMS 123C)
- contrast on primary: white 9.27, #10131A 2.01; AA text (4.5:1): white
- note: An older GMU guidelines page lists #006633/#FFCC33; brand guide used.

### vcu.edu : Virginia Commonwealth University
- primary #FFB300, secondary #000000
- source: https://compass.vcu.edu/guide/colors/
- derivation: hex given in the VCU web framework primary palette (VCU Gold PMS 130C; black)
- contrast on primary: white 1.79, #10131A 10.35; AA text (4.5:1): #10131A

### odu.edu : Old Dominion University
- primary #043657, secondary #828A8F
- source: https://www.odu.edu/university-communications/brand-toolkit/palette-fonts
- derivation: hex given (Monarch Blue; Silver Reign)
- contrast on primary: white 12.57, #10131A 1.48; AA text (4.5:1): white; FLAG: very dark
- note: Policy names PMS 540 blue and silver; blue is very dark.

### jmu.edu : James Madison University
- primary #450084, secondary #CBB677
- source: https://www.jmu.edu/identity/our-style/color.shtml
- derivation: hex given (JMU Purple PMS 2685; JMU Gold PMS 4515)
- contrast on primary: white 13.24, #10131A 1.40; AA text (4.5:1): white; FLAG: very dark
- note: JMU says the lighter gold must not be used for text on white.

### wm.edu : College of William and Mary
- primary #004E38, secondary #B79257
- source: https://brand.wm.edu/index.php/university-colors/
- derivation: hex given (W&M Green PMS 343C; W&M Gold PMS 465)
- contrast on primary: white 9.78, #10131A 1.90; AA text (4.5:1): white
- note: Accessible gold for text #866F45 per the library guide.

### radford.edu : Radford University
- primary #C2011B, secondary #003C71
- source: https://www.radford.edu/marketing-communication/_documents/radford-brand-guide.pdf
- derivation: hex given (Radford Red PMS 186; Blue Ridge PMS 541)
- contrast on primary: white 6.34, #10131A 2.93; AA text (4.5:1): white
- note: Brand guide is about three years old.

### ecu.edu : East Carolina University
- primary #592A8A, secondary #FEC923
- source: https://brand.ecu.edu/
- derivation: hex given (ECU Purple PMS 268; ECU Gold PMS 123)
- contrast on primary: white 9.89, #10131A 1.88; AA text (4.5:1): white
- note: Other ECU documents list #582C83 and #FFC702.

### uncc.edu : University of North Carolina at Charlotte
- primary #005035, secondary #A49665
- source: https://advancement.uncc.edu/university-communications/design-toolkit/color-palette
- derivation: hex given (Charlotte Green PMS 7484; Niner Gold PMS 7503)
- contrast on primary: white 9.55, #10131A 1.95; AA text (4.5:1): white
- note: CONFLICT: 2015 identity guide used #00703C (PMS 349); current toolkit used.

### uncg.edu : The University of North Carolina at Greensboro
- primary #0F2044, secondary #FFB71B
- source: https://uc.uncg.edu/brand-guide/university-colors/
- derivation: hex given (Navy PMS 2767 C; Gold PMS 1235 C)
- contrast on primary: white 16.03, #10131A 1.16; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Blue is near-black.

### uncw.edu : University of North Carolina at Wilmington
- primary #007680, secondary null
- source: https://www.uncw.edu/news/support-services/web-publishing/2025/09/branding-updates-and-web-impacts
- derivation: hex given in the 2025 branding update (signature teal PMS 7714)
- contrast on primary: white 5.38, #10131A 3.45; AA text (4.5:1): white
- note: Teal updated July 2025; older policy page said PMS 329. Navy accent hex differs between pages, so no secondary.

### appstate.edu : Appalachian State University
- primary #FFCC00, secondary #222222
- source: https://commtoolbox.appstate.edu/style/colors
- derivation: hex given (App State Gold; process black #222222)
- contrast on primary: white 1.51, #10131A 12.29; AA text (4.5:1): #10131A
- note: Brand guide lists black #010101.

### wcu.edu : Western Carolina University
- primary #592C88, secondary #C1A875
- source: https://www.wcu.edu/discover/communications-and-marketing/wcu-brand/visual-identity/wcu-colors.aspx
- derivation: hex given (WCU Purple PMS 267 C; Catamount Gold PMS 467 C)
- contrast on primary: white 9.81, #10131A 1.89; AA text (4.5:1): white
- note: Club sports guide uses a slightly different purple.

### ncat.edu : North Carolina A&T State University
- primary #004684, secondary #FDB927
- source: https://relations.ncat.edu/branding/color-palette.html
- derivation: hex given (Aggie Blue PMS 288; Aggie Gold PMS 123)
- contrast on primary: white 9.51, #10131A 1.95; AA text (4.5:1): white
- note: ncat.edu/styleguide page lists other blues (#022761, #002D74).

### furman.edu : Furman University
- primary #582C83, secondary #54585A
- source: https://www.furman.edu/wp-content/uploads/2019/Brand-Standards-Guide.pdf
- derivation: hex given (Furman Purple PMS 268; Furman Gray PMS 425)
- contrast on primary: white 9.99, #10131A 1.86; AA text (4.5:1): white
- note: 2019 guide.

### coastal.edu : Coastal Carolina University
- primary #006F71, secondary #A27752
- source: https://www.coastal.edu/media/2024siteassets/contentassets/documents/universitymarketingandcommunication/Coastal_Carolina_University_Brand_Guide_2024.pdf
- derivation: hex given (Teal PMS 322; Bronze PMS 875)
- contrast on primary: white 5.98, #10131A 3.11; AA text (4.5:1): white

### winthrop.edu : Winthrop University
- primary #6B0D0E, secondary #F8C23A
- source: https://www.winthrop.edu/ucm/visual-identity/colors/primary-colors.aspx
- derivation: hex given (Garnet PMS 202C; Gold PMS 136C)
- contrast on primary: white 12.43, #10131A 1.49; AA text (4.5:1): white; FLAG: very dark
- note: Garnet is very dark.

### byu.edu : Brigham Young University
- primary #002E5D, secondary null
- source: https://brand.byu.edu/brand-guidelines/colors/
- derivation: hex given (Navy PMS 648 C)
- contrast on primary: white 13.56, #10131A 1.37; AA text (4.5:1): white; FLAG: very dark
- note: Secondary Royal hex differs across BYU pages (#0062B8, #0047BA, #003DA5), so none is stored.

### weber.edu : Weber State University
- primary #492365, secondary #4A494D
- source: https://www.weber.edu/brand/colors.html
- derivation: hex given (Wildcat Purple PMS 2617; University Gray PMS 425)
- contrast on primary: white 12.27, #10131A 1.51; AA text (4.5:1): white; FLAG: very dark

### wichita.edu : Wichita State University
- primary #FFDB00, secondary #000000
- source: https://www.wichita.edu/services/strategic_communications/brand_standards/_documents/visual-standards-2022.pdf
- derivation: hex given (Shocker Yellow PMS 116C; black)
- contrast on primary: white 1.37, #10131A 13.61; AA text (4.5:1): #10131A; FLAG: NEAR-WHITE
- note: Manual says hex is for reference; 2022 edition.

### und.edu : University of North Dakota
- primary #009A44, secondary null
- source: https://campus.und.edu/brand/color.html
- derivation: hex given (UND Green PMS 347)
- contrast on primary: white 3.68, #10131A 5.05; AA text (4.5:1): #10131A

### ndsu.edu : North Dakota State University
- primary #00583D, secondary #FFC425
- source: https://www.ndsu.edu/sites/default/files/documents/NDSU-Brand-Basics.pdf
- derivation: hex given (NDSU Green PMS 343; Yellow PMS 123)
- contrast on primary: white 8.53, #10131A 2.18; AA text (4.5:1): white

### sdstate.edu : South Dakota State University
- primary #0033A0, secondary #FFD100
- source: https://www.sdstate.edu/university-marketing-communications/sdstate-graphic-identity-standards/university-colors
- derivation: hex given (SDSU Blue PMS 286; SDSU Yellow PMS 109)
- contrast on primary: white 10.60, #10131A 1.75; AA text (4.5:1): white

### montana.edu : Montana State University - Bozeman
- primary #162960, secondary #F4B425
- source: https://www.montana.edu/marketing/logo-use-guide.html
- derivation: hex given (MSU Blue PMS 281; MSU Gold PMS 124 web values)
- contrast on primary: white 13.81, #10131A 1.35; AA text (4.5:1): white; FLAG: very dark
- note: Print hex #0D2C6C/#FEBE10 also listed; older page used #003399/#FFCC00. Blue is very dark.

### umt.edu : University of Montana
- primary #70002E, secondary null
- source: https://www.umt.edu/brand/colors.php
- derivation: hex given (Griz Maroon PMS 209 C)
- contrast on primary: white 12.15, #10131A 1.53; AA text (4.5:1): white; FLAG: very dark
- note: WEAKER: brand colour table is old per search metadata; silver (the other institutional colour) has no hex here.

### uidaho.edu : University of Idaho
- primary #F1B300, secondary #808080
- source: https://www.uidaho.edu/brand
- derivation: hex given (Pride Gold PMS 3514 C; Silver)
- contrast on primary: white 1.88, #10131A 9.90; AA text (4.5:1): #10131A
- note: Brand page is about three years old.

### pdx.edu : Portland State University
- primary #6D8D24, secondary #213921
- source: https://www.pdx.edu/university-communications/tools-and-templates/brand-colors
- derivation: hex given (PSU Green PMS 7496; Forest Green PMS 553 C)
- contrast on primary: white 3.83, #10131A 4.85; AA text (4.5:1): #10131A

### wwu.edu : Western Washington University
- primary #003F87, secondary #FFC61E
- source: https://marcom.wwu.edu/files/2021-01/8.5x11-coated-3up%20(1).pdf
- derivation: hex given (Dark Blue PMS 294; Yellow PMS 123)
- contrast on primary: white 10.19, #10131A 1.82; AA text (4.5:1): white
- note: Other WWU pages list slightly different light blue/red/dark green.

### unr.edu : University of Nevada, Reno
- primary #041E42, secondary #8A8D8F
- source: https://med.unr.edu/marketing-and-communications/brand-guide/brand-style
- derivation: hex given (Nevada Blue PMS 282C; Nevada Silver PMS 877)
- contrast on primary: white 16.54, #10131A 1.12; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: WEAKER: School of Medicine page on unr.edu; the central UNR brand page was not found.

### csusb.edu : California State University, San Bernardino
- primary #0065BD, secondary null
- source: https://www.csusb.edu/sites/default/files/upload/file/CSUSB-Brand-Manual.pdf
- derivation: hex given in 2017 brand manual (Coyote Blue PMS 300)
- contrast on primary: white 5.84, #10131A 3.18; AA text (4.5:1): white
- note: WEAKER: 2017 manual; secondary gray differs between CSUSB documents so none stored.

### fresnostate.edu : California State University, Fresno
- primary #C41230, secondary #13284C
- source: https://marcomm.fresnostate.edu/color.html
- derivation: hex given (Cardinal Red PMS 186; Blue PMS 2767)
- contrast on primary: white 6.04, #10131A 3.08; AA text (4.5:1): white
- note: Blue is near-black.

### csuchico.edu : California State University, Chico
- primary #9D2235, secondary #75787B
- source: https://www.csuchico.edu/about/brand/visual-identity/colors-and-typefaces.shtml
- derivation: hex given (Chico Red PMS 201 C; Cornerstone Gray PMS Cool Gray 9 C)
- contrast on primary: white 7.74, #10131A 2.40; AA text (4.5:1): white

### nmsu.edu : New Mexico State University
- primary #8C0B42, secondary null
- source: https://brand.nmsu.edu/color/index.html
- derivation: hex given (Aggie Crimson PMS 208)
- contrast on primary: white 9.37, #10131A 1.98; AA text (4.5:1): white
- note: Athletics uses a slightly different crimson.

### mines.edu : Colorado School of Mines
- primary #21314D, secondary #D2492A
- source: https://mines.edu/webcentral/colors
- derivation: hex given (Dark Blue PMS 533; Colorado Red PMS 173)
- contrast on primary: white 13.03, #10131A 1.43; AA text (4.5:1): white; FLAG: very dark
- note: Hex repeated in the 2013 graphic standards guide; blue is very dark.

### umbc.edu : University of Maryland, Baltimore County
- primary #FDB515, secondary #000000
- source: https://styleguide.umbc.edu/umbc-colors/
- derivation: hex given (UMBC Gold PMS 1235C; UMBC Black)
- contrast on primary: white 1.78, #10131A 10.44; AA text (4.5:1): #10131A
- note: Brand PDF has a typo in gold RGB; style guide pages used.

### towson.edu : Towson University
- primary #FFBB00, secondary #3C3C3C
- source: https://www.towson.edu/brand/visual-guidelines/color.html
- derivation: hex given (Towson Gold PMS 116 U; Graphite PMS 447 C)
- contrast on primary: white 1.70, #10131A 10.94; AA text (4.5:1): #10131A

### howard.edu : Howard University
- primary #003A63, secondary #E51937
- source: https://ouc.howard.edu/our-services/creative-branding-multimedia/colors-typography
- derivation: hex given (Dark Midnight Blue PMS 2965; Crimson PMS 186)
- contrast on primary: white 11.76, #10131A 1.58; AA text (4.5:1): white; FLAG: very dark
- note: Some rows of the page have inconsistent RGB.

### udel.edu : University of Delaware
- primary #00539F, secondary #FFD200
- source: https://www.udel.edu/content/dam/udelImages/ocm/style-guide/signage-style-guide.pdf
- derivation: hex given (Delaware Blue PMS 2945 C; Yellow-Gold PMS 109 C)
- contrast on primary: white 7.67, #10131A 2.42; AA text (4.5:1): white
- note: Signage style guide PDF.

### uconn.edu : University of Connecticut
- primary #000E2F, secondary #7C878E
- source: https://brand.uconn.edu/guidelines-usage/color-palette/
- derivation: hex given (UConn Navy PMS 289; Grey PMS 430)
- contrast on primary: white 19.02, #10131A 1.02; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Navy is near-black; 2019 guide lists #1B2E67 for small spaces.

### uvm.edu : University of Vermont
- primary #154734, secondary #FFD100
- source: https://www.uvm.edu/stratcomm/brand/color-palette
- derivation: hex given (Catamount Green PMS 3435 C; Gold PMS 109 C)
- contrast on primary: white 10.59, #10131A 1.75; AA text (4.5:1): white
- note: Athletics guide uses green #005838.

### umaine.edu : University of Maine
- primary #082E58, secondary #79BDE8
- source: https://umaine.edu/marketingandcommunications/brand/visual-identity/
- derivation: hex given (dark blue PMS 289; light blue PMS 292)
- contrast on primary: white 13.62, #10131A 1.36; AA text (4.5:1): white; FLAG: very dark
- note: Cooperative Extension standards give #002A5B/#B0D7FF.

### caltech.edu : California Institute of Technology
- primary #FF6C0C, secondary null
- source: https://identity.caltech.edu/colors
- derivation: hex given (Caltech Orange PMS 1585c)
- contrast on primary: white 2.84, #10131A 6.55; AA text (4.5:1): #10131A

### scu.edu : Santa Clara University
- primary #A32035, secondary #862633
- source: https://www.scu.edu/umc/brand/colors/
- derivation: hex given (Santa Clara Red PMS 201 C; Bronco Red PMS 202 C)
- contrast on primary: white 7.46, #10131A 2.49; AA text (4.5:1): white
- note: School notes a deeper red (202) also appears in print.

### lmu.edu : Loyola Marymount University
- primary #0076A5, secondary #AB0C2F
- source: https://brand.lmu.edu/identitystandards/colors/
- derivation: hex given (blue PMS 2185; crimson PMS 207)
- contrast on primary: white 5.08, #10131A 3.66; AA text (4.5:1): white
- note: Which of the two is 'primary' is not stated in the search summary; blue listed first.

### pepperdine.edu : Pepperdine University
- primary #1E2859, secondary #E65526
- source: https://community.pepperdine.edu/imc/resources/style-guide/official-colors/
- derivation: hex given (Pepperdine Blue PMS 281; Orange PMS 166)
- contrast on primary: white 13.97, #10131A 1.33; AA text (4.5:1): white; FLAG: very dark
- note: Web styling page uses #00205C/#C25700; print palette used here.

### calpoly.edu : California Polytechnic State University, San Luis Obispo
- primary #154734, secondary null
- source: https://ucm.calpoly.edu/color-guidelines
- derivation: hex given (Poly Green PMS 3435 C)
- contrast on primary: white 10.59, #10131A 1.75; AA text (4.5:1): white

### ucsf.edu : University of California, San Francisco
- primary #052049, secondary #FEB80A
- source: https://identity.ucsf.edu/brand-guide/color
- derivation: hex given (UCSF Navy PMS 7463; Yellow PMS 7549)
- contrast on primary: white 16.04, #10131A 1.16; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Navy is near-black.

### tsu.edu : Texas Southern University
- primary #75263B, secondary null
- source: https://tsu.edu/about/administration/marketing-and-communications/documents/tsu-brand-standard-guidelines_0322.pdf
- derivation: hex given (Maroon PMS 209)
- contrast on primary: white 10.02, #10131A 1.86; AA text (4.5:1): white
- note: Gray hex in the same table is inconsistent, so no secondary.

### pvamu.edu : Prairie View A&M University
- primary #582C83, secondary #EAAA00
- source: https://www.pvamu.edu/marcomm/resources/colors/
- derivation: hex given (Purple PMS 268 C; Gold PMS 124 C)
- contrast on primary: white 9.99, #10131A 1.86; AA text (4.5:1): white

### trinity.edu : Trinity University
- primary #870A0F, secondary null
- source: https://trinity.edu/brand/visual/colors
- derivation: hex given (Trinity Maroon PMS 7623)
- contrast on primary: white 10.09, #10131A 1.84; AA text (4.5:1): white

### acu.edu : Abilene Christian University
- primary #4F2170, secondary null
- source: https://acu.edu/wp-content/uploads/2024/10/ACU_Branding-and-Editorial-style-guide.pdf
- derivation: hex given (ACU Purple PMS 268)
- contrast on primary: white 11.77, #10131A 1.58; AA text (4.5:1): white; FLAG: very dark
- note: WEAKER: July 2020 guide; very dark.

### uca.edu : University of Central Arkansas
- primary #582C83, secondary #7C878E
- source: https://uca.edu/toolkit/official-colors/
- derivation: hex given (Purple PMS 268; Gray PMS 430)
- contrast on primary: white 9.99, #10131A 1.86; AA text (4.5:1): white

### astate.edu : Arkansas State University
- primary #CC092F, secondary #000000
- source: http://wt-dc-prod.astate.edu/a/marketing/pcs/graphic-standards/logos-colors-fonts/university-colors/
- derivation: hex given (A-State Red PMS 186; black)
- contrast on primary: white 5.76, #10131A 3.23; AA text (4.5:1): white
- note: WEAKER: page served from a wt-dc-prod.astate.edu host.

### ualr.edu : University of Arkansas - Little Rock
- primary #6E2639, secondary #A7A9AC
- source: https://ualr.edu/communications/colors/
- derivation: hex given (Maroon PMS 209c; Silver PMS 877c)
- contrast on primary: white 10.50, #10131A 1.77; AA text (4.5:1): white

### southernct.edu : Southern Connecticut State University
- primary #003399, secondary null
- source: https://www.southernct.edu/icm/branding/visual-identity
- derivation: hex given as digital equivalent of Pantone Reflex Blue
- contrast on primary: white 10.86, #10131A 1.71; AA text (4.5:1): white
- note: Athletics guide uses Reflex Blue plus Process Yellow.

### hawaii.edu : University of Hawaii System
- primary #B3995D, secondary null
- source: https://www.hawaii.edu/offices/communications/standards/graphics-standards/signatures/
- derivation: hex given on graphics standards page (UH System signature, PMS 872 gold)
- contrast on primary: white 2.75, #10131A 6.75; AA text (4.5:1): #10131A
- note: WEAKER: signature colour of the UH System; individual campuses use their own colours (e.g. Manoa green #024731).

### iup.edu : Indiana University of Pennsylvania
- primary #9D2235, secondary #5E5F5F
- source: https://www.iup.edu/marcom/visual-guide/index.html
- derivation: hex given (IUP Crimson PMS 201 C; IUP Gray)
- contrast on primary: white 7.74, #10131A 2.40; AA text (4.5:1): white

### wcupa.edu : West Chester University of Pennsylvania
- primary #512D6D, secondary #FFC72C
- source: https://www.wcupa.edu/brand/colors.aspx
- derivation: hex given (Classic Purple PMS 269; Classic Gold PMS 123)
- contrast on primary: white 10.79, #10131A 1.72; AA text (4.5:1): white
- note: A May 2026 update says a refined palette is in progress (Elemental Purple #382140 / Gold #FFE800 listed as primary on the guide).

### usd.edu : University of South Dakota
- primary #D21533, secondary null
- source: https://td.usd.edu/TDClient/33/Portal/KB/ArticleDet?ID=5155
- derivation: hex given on the USD web colour standards page (Coyote Red PMS 186)
- contrast on primary: white 5.39, #10131A 3.45; AA text (4.5:1): white
- note: WEAKER: IT knowledge-base page on usd.edu, about three years old.

### mnsu.edu : Minnesota State University, Mankato
- primary #49306E, secondary #FEBD11
- source: https://mankato.mnsu.edu/brand-hub/design-resources/colors/
- derivation: hex given (primary purple; primary gold)
- contrast on primary: white 10.87, #10131A 1.71; AA text (4.5:1): white
- note: Page about 900 days old per search metadata.

### bsu.edu : Ball State University
- primary #BA0C2F, secondary #54585A
- source: https://www.bsu.edu/about/administrativeoffices/marketing-communications/brand-resources/colors
- derivation: hex given (Cardinal Red PMS 200 C; dark gray PMS 425)
- contrast on primary: white 6.60, #10131A 2.82; AA text (4.5:1): white

### isu.edu : Idaho State University
- primary #F47920, secondary null
- source: https://www.isu.edu/brand/design/colors/
- derivation: hex given (Roarange PMS 165)
- contrast on primary: white 2.76, #10131A 6.73; AA text (4.5:1): #10131A
- note: Idaho State; brand pages and PDF differ by 1-3 RGB units.

### morgan.edu : Morgan State University
- primary #1B4383, secondary #F47937
- source: https://www1.morgan.edu/toolkit/official-colors/
- derivation: hex given (Morgan Blue PMS 288; Morgan Orange PMS 1655)
- contrast on primary: white 9.65, #10131A 1.93; AA text (4.5:1): white

### valpo.edu : Valparaiso University
- primary #5C3000, secondary #F5B80A
- source: https://www.valpo.edu/about/marcom/brand/brand-tool-kit/color-palettes/
- derivation: hex given (Brown PMS 1535 C; Gold PMS 1235 C)
- contrast on primary: white 11.18, #10131A 1.66; AA text (4.5:1): white
- note: Brown is very dark.

### butler.edu : Butler University
- primary #13294B, secondary null
- source: https://www.butler.edu/marketing/brand/color-palette/
- derivation: hex given (Butler Blue PMS 2767 C)
- contrast on primary: white 14.52, #10131A 1.28; AA text (4.5:1): white; FLAG: very dark
- note: Near-black.

### seattleu.edu : Seattle University
- primary #AA0000, secondary null
- source: https://www.seattleu.edu/marcom/brand/colors-and-icons/
- derivation: hex given (SU Red PMS 200C; adjusted for accessibility)
- contrast on primary: white 7.75, #10131A 2.40; AA text (4.5:1): white

### usfca.edu : University of San Francisco
- primary #00543C, secondary #FDBB30
- source: https://myusf.usfca.edu/sites/default/files/documents/OMC/graphic-standards-manual.pdf
- derivation: hex given (USF Green PMS 554 C; USF Gold PMS 1235 C)
- contrast on primary: white 9.00, #10131A 2.06; AA text (4.5:1): white

### nsula.edu : Northwestern State University
- primary #663399, secondary #FF6600
- source: https://documentproviderviewer.nsula.edu/?id=11285
- derivation: hex given in NSU visual branding guidelines (purple PMS 267; athletic orange PMS 165)
- contrast on primary: white 8.41, #10131A 2.21; AA text (4.5:1): white
- note: Orange is the athletics accent; official second colour is white.

### mc.edu : Mississippi College
- primary #0C2340, secondary #C99700
- source: https://www.mc.edu/offices/marketing/university-branding/brand-toolkit/visual-guidelines/colors
- derivation: hex given (Pantone 289 blue; Pantone 117 gold)
- contrast on primary: white 15.79, #10131A 1.18; AA text (4.5:1): white; FLAG: NEAR-BLACK
- note: Near-black blue.

### alcorn.edu : Alcorn State University
- primary #512D6D, secondary #CC8A00
- source: https://www.alcorn.edu/marketing-and-communication/identity-standards/
- derivation: hex given (Purple PMS 269; Gold PMS 131)
- contrast on primary: white 10.79, #10131A 1.72; AA text (4.5:1): white
- note: 2025 style guide lists the same two hex values.

### columbusstate.edu : Columbus State University
- primary #003359, secondary #C60C30
- source: https://www.columbusstate.edu/scm/_docs/CSU_Brand_Guidelines-1.pdf
- derivation: hex given (Columbus State Blue PMS 540 C; Red PMS 186 C)
- contrast on primary: white 12.98, #10131A 1.43; AA text (4.5:1): white; FLAG: very dark

### gcsu.edu : Georgia College
- primary #1F3D7B, secondary #245C4F
- source: https://my.gcsu.edu/sites/default/files/2024-09/GCSU%20Art%20Sheet.pdf
- derivation: hex given on the 2023 art sheet (blue; green)
- contrast on primary: white 10.44, #10131A 1.78; AA text (4.5:1): white
- note: Which of blue or green is primary is not stated; About page says blue and green.

### sewanee.edu : Sewanee, University of the South
- primary #582C83, secondary #FFB81C
- source: https://new.sewanee.edu/offices/university-offices/marketing-communications/graphic-identity-standards/
- derivation: hex given (Purple PMS 268; Gold PMS 1235)
- contrast on primary: white 9.99, #10131A 1.86; AA text (4.5:1): white

### austincc.edu : Austin Community College
- primary #4D1979, secondary #00B2A9
- source: https://brand.austincc.edu/acc-brand-visual-identity/acc-official-colors/
- derivation: hex given (Riverbat Purple PMS 268 C; teal)
- contrast on primary: white 12.13, #10131A 1.53; AA text (4.5:1): white; FLAG: very dark
- note: Logo page lists different web codes for some accents.

### lonestar.edu : Lone Star College System
- primary #003768, secondary #B30838
- source: https://www.lonestar.edu/college-departments/marketing-communications/brand-and-logo-styleguide.htm
- derivation: hex given (blue PMS 540; red PMS 201)
- contrast on primary: white 12.02, #10131A 1.55; AA text (4.5:1): white; FLAG: very dark
- note: Hex read from the brand style guide; guides are several years old.

### valenciacollege.edu : Valencia College
- primary #BF311A, secondary #FDB913
- source: https://valenciacollege.edu/brand/color-palettes.php
- derivation: hex given (Valencia Red PMS 1805 C; Yellow)
- contrast on primary: white 5.72, #10131A 3.25; AA text (4.5:1): white

### mdc.edu : Miami Dade College
- primary #0032A0, secondary #5B6770
- source: https://www.mdc.edu/media/miami-dade-college/marketing-communications/documents/Official_Design_Guidelines_2025.pdf
- derivation: hex given as web colours (MDC Blue PMS 286; MDC Gray PMS 431)
- contrast on primary: white 10.69, #10131A 1.74; AA text (4.5:1): white

### broward.edu : Broward College
- primary #005596, secondary null
- source: https://www.broward.edu/design-system/colors.html
- derivation: hex given in the Broward design system (brand blue)
- contrast on primary: white 7.66, #10131A 2.42; AA text (4.5:1): white
- note: Signage standards use PMS 294M.

### dcccd.edu : Dallas County Community College
- primary #E52626, secondary #003385
- source: https://dcccd.edu/about/style/pages/collegecolors.aspx
- derivation: hex given (Dallas College Red PMS 485 C; Dallas College Blue)
- contrast on primary: white 4.53, #10131A 4.10; AA text (4.5:1): white
- note: WEAKER: page about 2,100 days old.

## Second pass: unverified (skipped)

- csulb.edu (California State University, Long Beach): only unit page hex, conflicting
- utep.edu (University of Texas at El Paso): search found guide PDF but no hex in snippet
- shsu.edu (Sam Houston State University): search found guide PDF but no hex in snippet
- valdosta.edu (Valdosta State University): color swatches are images, no hex text
- jsu.edu (Jacksonville State University): hex only in external brand guide
- fgcu.edu (Florida Gulf Coast University): hex only in PDF guide
- troy.edu (Troy University): swatch images only
- westga.edu (University of West Georgia): no brand page found
- jsums.edu (Jackson State University): only 2014 guide hex (#002147) seen
- memphis.edu (University of Memphis): conflicting; no official hex for Memphis Blue
- selu.edu (Southeastern Louisiana University): no brand page found
- nicholls.edu (Nicholls State University): no hex found
- subr.edu (Southern University and A&M College): PMS only
- gram.edu (Grambling State University): no codes found
- tuskegee.edu (Tuskegee University): only ~15-year-old manual
- morehouse.edu (Morehouse): no codes
- belmont.edu (Belmont University): page not readable via search
- lipscomb.edu (Lipscomb University): no codes seen
- rollins.edu (Rollins College): no codes seen
- stetson.edu (Stetson University): two brand docs conflict (#339933 vs #095540)
- fordham.edu (Fordham University): new maroon hex not published in results
- bc.edu (Boston College): no brand page found
- ilstu.edu (Illinois State University): no brand page found
- kent.edu (Kent State University): hex/RGB inconsistent in results
- rpi.edu (Rensselaer Polytechnic Institute): no hex found
- liberty.edu (Liberty University): brand guides conflict (#990000 vs #B72025)
- cofc.edu (College of Charleston): no brand page found
- uvu.edu (Utah Valley University): current #185C33 vs older #275D38 conflict
- nau.edu (Northern Arizona University): True Blue #003466 vs #002454 conflict
- ksu.edu (Kansas State University): search found no brand page
- creighton.edu (Creighton University): only Creighton Prep guide found
- unomaha.edu (University of Nebraska, Omaha): no hex given
- gonzaga.edu (Gonzaga University): only athletics guide hex
- uwm.edu (University of Wisconsin - Milwaukee): no hex found
- unh.edu (University of New Hampshire): no brand page found
- uri.edu (University of Rhode Island): no brand page found
- njit.edu (New Jersey Institute of Technology): no brand page found
- umass.edu (University of Massachusetts at Amherst): maroon conflict (#881C1C, #840028, refreshed digital value)
- cpp.edu (California Polytechnic State University, Pomona): no hex found
- sfsu.edu (San Francisco State University): no hex found
- csus.edu (California State University, Sacramento): Pantone only
- tamucc.edu (Texas A&M University - Corpus Christi): Pantone only
- lamar.edu (Lamar University): athletics guide, no clean hex map
- ut.edu (University of Tampa): no brand page found
- stevens.edu (Stevens Institute of Technology): no brand page found
- ucdenver.edu (University of Colorado at Denver): only school-level guides found
- unco.edu (University of Northern Colorado): no hex in results
- indstate.edu (Indiana State University): no brand page found
- montclair.edu (Montclair State University): no brand page found
- tcnj.edu (The College of New Jersey): no brand page found
- kean.edu (Kean College): Pantone only
- loyno.edu (Loyola University New Orleans): PMS only
- xula.edu (Xavier University of Louisiana): no hex
- deltastate.edu (Delta State University): no brand page found
- eckerd.edu (Eckerd College): no brand page found
- hccs.edu (Houston Community College): palette not readable; rebrand Sept 2025
- nvcc.edu (Northern Virginia Community College): no hex in results
- alamo.edu (Alamo Colleges District): RGB only; conversions would be mine
