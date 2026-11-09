# Kinship scope codebook

**Version:** 0.1 (draft, not yet calibrated)
**Status:** Proposed rules. Becomes v1.0 after the two-coder calibration in §8.
**Used by:** human reviewers, and as the instruction text for any automated relevance classifier. Change the rules here and nowhere else.

---

## 1. Definition

> **Kinship covers research on how economic advantage and disadvantage are passed between generations and between kin, through which channels, and how institutions strengthen or weaken that transmission.**

| Term | Meaning |
|---|---|
| **Advantage** | Economic resources (income, earnings, wealth) and what produces them: education, skills, occupation, health*, networks, and access to good places. |
| **Between generations and kin** | Parent → child, plus grandparents and further back, siblings (as a measure of shared family background), and in-laws through marriage. The main direction is downward, but flows between siblings and upward to parents count where they shape what is passed down. |
| **Passed** | The paper measures persistence across generations, or studies a channel or institution that produces, strengthens or weakens it. |

\* See open decision **D1**.

## 2. The core test

Apply two tests to every paper.

- **T1, family link.** The paper connects people across generations or within a family: linked parent and child records, sibling or multigenerational data, or a theoretical model of the family across generations.
- **T2, advantage.** An economic outcome, or a resource that produces one (see §1), sits on at least one side of that link.

## 3. Tiers

| Rule | Tier | Condition |
|---|---|---|
| **I1** | **Core** | Passes T1 **and** T2. |
| **I2** | **Adjacent** | Passes only one test, **and** the paper explicitly argues something about transmission, e.g. reports effects by parental income or discusses persistence across generations. |
| **I3** | **Out** | Fails both tests, or passes one without any argument about transmission, or meets an exclusion rule in §5. |

Applies to every tier:

- **I4, any discipline.** Economics, sociology, demography, law, biology and others. The venue doesn't matter, only the content.
- **I5, any design.** Empirical, theoretical, methodological or review papers. Any country, any historical period studied.
- **I6, relevance is not quality.** Scope is decided on relevance alone. Credibility and contribution are judged separately (see `registry/README.md`).

## 4. Categories and channels (these become site tags)

A paper gets one or more of these codes.

**A. Measuring persistence**
Income and earnings mobility (intergenerational elasticity, rank-rank correlations); wealth, education and occupational mobility; sibling correlations; multigenerational and grandparent effects; persistence of elites and surnames; differences in mobility by race, gender or region.

**B. Channels**

| Code | Channel | Examples |
|---|---|---|
| **B1** | Financial transfers | Bequests, inheritances, gifts during life, help with housing, division among siblings, bequest motives, effects of receiving an inheritance on heirs |
| **B2** | Investment in children | Parents' time and money, early childhood, schooling choices, parenting style, family size and birth order |
| **B3** | Endowments | Genetic vs environmental transmission, adoption and twin designs aimed at transmission, birth weight and early health |
| **B4** | Networks and access | Connections, nepotism, following a parent's occupation, family firms, legacy admissions |
| **B5** | Place | Neighbourhood sorting and neighbourhood effects as a channel for parents' resources |
| **B6** | Family formation | Assortative mating, divorce, single parenthood, stepfamilies, fertility differences by income or class |
| **B7** | Preferences and norms | Passing on risk attitudes, patience, work and gender norms, *when linked to economic outcomes* |

**C. Institutions and policy**
Inheritance and estate taxation, inheritance law, education reforms, admissions rules, family policy, welfare. Included when the paper measures effects by family background or across generations, or when the policy's purpose is transmission itself (inheritance tax, inheritance law).

**D. Data, methods, theory and reviews**
Measurement problems in estimating mobility (measurement error, life-cycle bias), linked register data, Becker–Tomes-type models, review articles.

## 5. Exclusion rules

| Rule | Excluded | Example |
|---|---|---|
| **E1** | Inequality at one point in time with no family dimension | Wage inequality from technological change; effect of wealth taxes on wealth accumulation |
| **E2** | Family background used only as a control variable | Returns-to-education papers controlling for parental schooling |
| **E3** | Sibling or twin fixed effects used only to identify something unrelated to the family | Twin estimates of the return to schooling |
| **E4** | Household decisions within one generation, with no effect on children and no transfers | Spousal bargaining, couples' labour supply or saving |
| **E5** | Passing on non-economic traits with no economic outcome | Religiosity, party identification |
| **E6** | Family events used only as a natural experiment for a question about a single generation | Sibling sex composition used to instrument mothers' fertility in a study of mothers' labour supply (Angrist & Evans 1998) |

Applies to every exclusion rule: **an exclusion is a default, not a veto.** A paper that meets E1–E6 but explicitly argues about transmission can still be Adjacent under I2.

## 6. Hard cases (rulings)

| ID | Case | Ruling |
|---|---|---|
| **H1** | Moving to Opportunity / neighbourhood effects on children | **Core** (B5): children of low-income families, adult outcomes |
| **H2** | Effects of receiving an inheritance on heirs (labour supply, saving, entrepreneurship, retirement) | **Core** (B1): what transferred resources do for the next generation |
| **H3** | Elder care by adult children; transfers to elderly parents | **Adjacent** (B1/B6). **Core** if linked to bequests or to exchange with parents |
| **H4** | Early-childhood program evaluations | **Core** if long-run outcomes are reported by family background; otherwise **Adjacent** |
| **H5** | Child penalty in mothers' earnings | **Adjacent**. **Core** if it covers passing gender norms from parents to children |
| **H6** | Assortative mating | **Adjacent**. **Core** if children's outcomes or inequality across generations are studied |
| **H7** | Inheritance or estate tax theory | **Core** (C) |
| **H8** | Estate-tax avoidance | **Adjacent** (C); **Core** if it is about how the estate is divided among heirs |
| **H9** | Polygenic indices and education | **Core** (B3) if it separates genetic from environmental transmission; otherwise **Out** |
| **H10** | Differences in fertility by income or class | **Adjacent** (B6) |
| **H11** | Inheritance law, including stepchild inheritance when there is no will | **Core** (C/B6) |
| **H12** | Birth weight and long-run outcomes | **Core** (B3) if D1 = health counts as an advantage on its own; otherwise **Adjacent** |
| **H13** | Divorce and marital-property law affecting couples' saving | **Adjacent** (B6/C, within one generation, E4) |
| **H14** | Transmission of crime, violence, risky behaviour or language, with no economic outcome measured | **Adjacent** (T1 met, T2 not). **Core** if the paper also measures education, earnings or another advantage |
| **H15** | Perceptions of mobility, preferences for redistribution, politics of mobility (no family data) | **Adjacent** (C): about how transmission is perceived or governed, not transmission itself |
| **H16** | "Intergenerational" meaning birth cohorts or generations of a population, not linked families | **Out**, unless immigrant generations or population-level transmission is the explicit object (then **Adjacent**) |
| **H17** | Welfare or benefit receipt passed from parents to children | **Core** (B7/C): benefit dependence counts as economic disadvantage |

New hard cases are added here with an ID, a ruling and the date. Rulings are never changed silently: changes are logged in §10.

## 7. What each coding decision stores

Every paper reviewed, by a person or a classifier, gets a record with these fields:

| Field | Values |
|---|---|
| `scope_tier` | `core` · `adjacent` · `out` |
| `scope_rules` | Rule IDs applied, e.g. `["I1","B1","H2"]` or `["I3","E1"]` |
| `channels` | One or more of `A`, `B1`–`B7`, `C`, `D` |
| `generations` | e.g. `parent-child`, `grandparent`, `siblings`, `multigenerational`, `in-laws` |
| `advantage` | e.g. `income`, `wealth`, `education`, `occupation`, `health`, `networks`, `place` |
| `rationale` | One sentence on why |
| `coder` | Person's initials, or `model:<id>` |
| `codebook_version` | e.g. `0.1` |

A decision must name at least one rule ID. If no rule fits, the paper goes to editorial review and the gap is logged in §10.

## 8. Calibration procedure

1. **Test set.** Draw 200 papers at random from the harvested candidates, plus the reference set in §9.
2. **Code independently.** Two coders apply this codebook without discussing it.
3. **Measure agreement.** Compute Cohen's κ on `scope_tier`. The target is **κ ≥ 0.75**.
4. **Resolve.** Discuss disagreements and record what was decided as a new rule or hard case.
5. **Repeat** with a fresh sample until the target is met, then set the version to 1.0.
6. **Machine check.** Run any classifier on the same samples. Report the share of human-Core papers it keeps (target ≥ 0.95) and the share of its Core picks that humans also call Core.

## 9. Reference set

Known papers with expected rulings. Any harvest and any classifier must reproduce these. If a ruling below proves wrong, fix the rules, not just the row.

### Papers on the site (`data/papers.json`)

| Paper | Expected | Codes |
|---|---|---|
| Chetty, Hendren, Kline & Saez 2014, QJE, *Where Is the Land of Opportunity?* | Core | A |
| Boserup, Kopczuk & Kreiner 2016, AER P&P, *The Role of Bequests in Shaping Wealth Inequality* | Core | B1 |
| Adermon, Lindahl & Waldenström 2018, EJ, *Intergenerational Wealth Mobility and the Role of Inheritance* | Core | A, B1 |
| Chetty, Hendren & Katz 2016, AER, *Moving to Opportunity* | Core | B5 (H1) |
| Black, Devereux & Salvanes 2005, QJE, *The More the Merrier?* | Core | B2 |
| **Voena 2015, AER, *Yours, Mine, and Ours*** | **Adjacent** | B6, C (H13) |
| Chetty & Hendren 2018, QJE, *Neighborhoods I* and *II* | Core | B5, A |
| Black, Devereux & Salvanes 2007, QJE, *From the Cradle to the Labor Market?* | Core / Adjacent | B3 (H12, depends on D1) |
| Chetty, Friedman, Saez, Turner & Yagan, *Mobility Report Cards* | Core | A, C |
| Boserup, Kopczuk & Kreiner, *Born with a Silver Spoon?* | Core | A, B1 |
| Doepke & Zilibotti, *Parenting with Style* | Core | B2, B7, D |

Note: under these rules, Voena 2015 is Adjacent, not Core. It should either be marked Adjacent on the site or replaced as a featured paper.

### Inheritance library (`Library/…/Family structure/Inheritance/Literature`)

| Paper | Expected | Codes |
|---|---|---|
| Tomes 1981, JPE, *The Family, Inheritance, and the Intergenerational Transmission of Inequality* | Core | A, B1, D |
| Bernheim, Shleifer & Summers 1985, JPE, *The Strategic Bequest Motive* | Core | B1 |
| Cox 1987, JPE, *Motives for Private Income Transfers* | Core | B1 |
| Altonji, Hayashi & Kotlikoff 1992, AER, *Is the Extended Family Altruistically Linked?* | Core | B1 |
| Altonji, Hayashi & Kotlikoff 1997, JPE, *Parental Altruism and Inter Vivos Transfers* | Core | B1 |
| Cox & Rank 1992, REStat, *Inter-Vivos Transfers and Intergenerational Exchange* | Core | B1 |
| Holtz-Eakin, Joulfaian & Rosen 1993, QJE, *The Carnegie Conjecture* | Core | B1 (H2) |
| Holtz-Eakin, Joulfaian & Rosen 1994, RAND, *Entrepreneurial Decisions and Liquidity Constraints* | Core | B1 (H2) |
| Joulfaian & Wilhelm 1994, JHR, *Inheritance and Labor Supply* | Core | B1 (H2) |
| Wilhelm 1996, AER, *Bequest Behavior and the Effect of Heirs' Earnings* | Core | B1 |
| McGarry 1999, JPubE, *Inter Vivos Transfers and Intended Bequests* | Core | B1 |
| McGarry 2001, JPubE, *The Cost of Equality: Unequal Bequests and Tax Avoidance* | Core | B1, C (H8) |
| Laitner & Ohlsson 2001, JPubE, *Bequest Motives: A Comparison of Sweden and the United States* | Core | B1 |
| Behrman & Rosenzweig 2004, REStat, *Parental Allocations to Children* | Core | B1 |
| Light & McGarry, *Why Parents Play Favorites* | Core | B1 |
| Kopczuk & Lupton 2007, REStud, *To Leave or Not to Leave* | Core | B1 |
| Brown 2006, JHR, *Informal Care and the Division of End-of-Life Transfers* | Core | B1 (H3, linked to bequests) |
| Brown, Coile & Weisbenner 2010, REStat, *The Effect of Inheritance Receipt on Retirement* | Core | B1 (H2) |
| Hochguertel & Ohlsson 2009, JAE, *Compensatory Inter Vivos Gifts* | Core | B1 |
| Elinder, Erixson & Waldenström 2018, *Inheritance and Wealth Inequality* | Core | B1 |
| Erixson & Ohlsson 2019, JPopE, *Estate Division: Equal Sharing, Exchange Motives, and Cinderella Effects* | Core | B1, B6 |
| Fagereng, Mogstad & Rønning 2021, JPE, *Why Do Wealthy Parents Have Wealthy Children?* | Core | A, B3 |
| Palomino, Marrero, Nolan & Rodríguez 2022, OEP, *Wealth Inequality, Intergenerational Transfers, and Family Background* | Core | A, B1 |
| Nekoei & Seim 2023, REStud, *How Do Inheritances Shape Wealth Inequality?* | Core | B1 |
| Francesconi, Pollak & Tabasso 2023, EER, *Unequal Bequests* | Core | B1 |
| Druedahl & Martinello, *Long-Run Saving Dynamics: Evidence from Unexpected Inheritances* | Core | B1 (H2) |
| Piketty & Saez 2013, Econometrica, *A Theory of Optimal Inheritance Taxation* | Core | C (H7) |
| Erola & Jalovaara 2017, Social Forces, *The Replaceable* | Core | A, B6 (I4) |
| Pettay et al. 2023, Human Nature, *Parental Investment by Birth Fathers and Stepfathers* | Core | B2, B6 (I4) |
| Cox 2007, JEP, *Biological Basics and the Economics of the Family* | Core | B3, D |
| Konrad, Künemund, Lommerud & Robledo, *Geography of the Family* | Adjacent | B6 (H3) |
| Pezzin & Schone 1999, Demography, *Parental Marital Disruption and Intergenerational Transfers* | Adjacent | B1, B6 (H3) |
| US law articles on stepchild intestacy (Law folder) | Core | C, B6 (H11) |
| Jakobsen, Jakobsen, Kleven & Zucman 2020, QJE, *Wealth Taxation and Wealth Accumulation* | **Out** | E1 |
| Kalmijn 2013, JMF, *Adult Children's Relationships With Married Parents, Divorced Parents, and Stepparents* | **To code** | Boundary test for E5 vs H3 |

Note: Jakobsen et al. is a useful **negative** case. It belongs in the research library but not on the site: it is about wealth accumulation, not transmission.

## 10. Open decisions and change log

### Open decisions

- **D1, is health an advantage in its own right?**
  - **Proposed:** yes. Birth weight and early health are major channels.
  - **If no:** health counts only when linked to an economic outcome, and H12 becomes Adjacent.
- **D2, are Adjacent papers shown on the site?**
  - **Proposed:** yes, marked as a separate tier.
  - **If no:** Adjacent papers are kept internally for discovery only.
- **D3, publication date window.**
  - The scope itself has no date limit (Tomes 1981 is Core).
  - The harvest window, e.g. 1990 onward, is a separate operational choice.

### Change log

| Date | Version | Change |
|---|---|---|
| 2026-11-09 | 0.1 | First draft: definition, tests T1–T2, tiers I1–I6, categories A–D, exclusions E1–E6, hard cases H1–H13, reference set. |
| 2026-11-09 | 0.1 | Added H14–H17 from first coding pass of the 403-paper seed list (`registry/seed/scope_coding.csv`). They record rulings applied in that pass. |
