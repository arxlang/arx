# Release Notes
---

## [0.6.1](https://github.com/arxlang/arx/compare/0.6.0...0.6.1) (2026-04-18)


### Bug Fixes

* Fix arx test implementation ([#52](https://github.com/arxlang/arx/issues/52)) ([4fe9e85](https://github.com/arxlang/arx/commit/4fe9e85c160fa1fd997b2e0a099a98d67b9dc174))

# [0.6.0](https://github.com/arxlang/arx/compare/0.5.0...0.6.0) (2026-04-18)


### Features

* **testing:** preserve shared top-level declarations in arx test wrappers; Add assert statement ([#51](https://github.com/arxlang/arx/issues/51)) ([83a6591](https://github.com/arxlang/arx/commit/83a6591c2317dc6d6ea52d12ad4a95096a5a8443))

# [0.5.0](https://github.com/arxlang/arx/compare/0.4.0...0.5.0) (2026-04-16)


### Features

* Add support for import/import-from ([#50](https://github.com/arxlang/arx/issues/50)) ([08c53ab](https://github.com/arxlang/arx/commit/08c53ab1aed5c21399193f9387f9cd93f8bb91ae))

# [0.4.0](https://github.com/arxlang/arx/compare/0.3.4...0.4.0) (2026-04-16)


### Features

* Add support for  classes ([#49](https://github.com/arxlang/arx/issues/49)) ([7c8b073](https://github.com/arxlang/arx/commit/7c8b073a2aeb780b3601f683478c0a6b17511477))

## [0.3.4](https://github.com/arxlang/arx/compare/0.3.3...0.3.4) (2026-04-02)


### Bug Fixes

* correct _default_value_for_type for temporal and unsupported types ([#36](https://github.com/arxlang/arx/issues/36)) ([93d7b13](https://github.com/arxlang/arx/commit/93d7b13fdd4626c75cd7c722ea473392b2f3e650))
* **refactor:** Update irx and update its usage; rename classes ([#39](https://github.com/arxlang/arx/issues/39)) ([c95c47c](https://github.com/arxlang/arx/commit/c95c47ce320069759a022623a6b1064280d0459b))

## [0.3.3](https://github.com/arxlang/arx/compare/0.3.2...0.3.3) (2026-03-06)


### Bug Fixes

* Update astx and irx; mermaid is optional now ([#35](https://github.com/arxlang/arx/issues/35)) ([37b3415](https://github.com/arxlang/arx/commit/37b341539eb4dd6989721dc43beb0d1d0e4d2327))

## [0.3.2](https://github.com/arxlang/arx/compare/0.3.1...0.3.2) (2026-03-06)


### Bug Fixes

* Fix compilation issues with PIE ([#34](https://github.com/arxlang/arx/issues/34)) ([4d043b2](https://github.com/arxlang/arx/commit/4d043b20f9d175e29d0469e563b543ccc1eff536))
* Returning type is now required ([#33](https://github.com/arxlang/arx/issues/33)) ([938a8b1](https://github.com/arxlang/arx/commit/938a8b1b847983fea06576e88324785c090f0c19))

## [0.3.1](https://github.com/arxlang/arx/compare/0.3.0...0.3.1) (2026-03-06)


### Bug Fixes

* Fix typing, tests, print, system; add more tests ([#32](https://github.com/arxlang/arx/issues/32)) ([21e4639](https://github.com/arxlang/arx/commit/21e4639c416666f3cf09a345350c1da9ab5e090e))

# [0.3.0](https://github.com/arxlang/arx/compare/0.2.0...0.3.0) (2026-03-06)


### Features

* Add support for loops, cast, print, datatypes, etc ([#31](https://github.com/arxlang/arx/issues/31)) ([3b9b27a](https://github.com/arxlang/arx/commit/3b9b27ab068ed5cd8eeafbae79d5d11372bc63c3))
* **syntax:** Support for Docstring syntax ([#29](https://github.com/arxlang/arx/issues/29)) ([2bb1f8b](https://github.com/arxlang/arx/commit/2bb1f8b0a784efe221d2ad890edc0a55014e741e))

# [0.2.0](https://github.com/arxlang/arx/compare/0.1.1...0.2.0) (2025-08-07)


### Bug Fixes

* Fix usage of FunctionCall ([#15](https://github.com/arxlang/arx/issues/15)) ([f7f61c0](https://github.com/arxlang/arx/commit/f7f61c014cc7f400ae6af2e89cbbf9f3907f9b3a))


### Features

* Add support for blocks of nodes ([#6](https://github.com/arxlang/arx/issues/6)) ([1fd099f](https://github.com/arxlang/arx/commit/1fd099fa7b505998e853b867039c6041005afe87))
* Move the AST output to YAML format ([#7](https://github.com/arxlang/arx/issues/7)) ([6a8e10f](https://github.com/arxlang/arx/commit/6a8e10f8a3a7d49af466342483cc42849b263153))
* Support multiple input files ([#8](https://github.com/arxlang/arx/issues/8)) ([ad31064](https://github.com/arxlang/arx/commit/ad31064baaf341a0a90da98016acc126c2e308e0))
* Use ASTx and IRx as core libraries for AST and code generation ([#14](https://github.com/arxlang/arx/issues/14)) ([b730859](https://github.com/arxlang/arx/commit/b730859e98ecc1f3e09a346ba634377d777e6617))

## [0.1.1](https://github.com/arxlang/arx/compare/0.1.0...0.1.1) (2023-06-26)


### Bug Fixes

* Change package name to arxlang ([#2](https://github.com/arxlang/arx/issues/2)) ([e30c937](https://github.com/arxlang/arx/commit/e30c9378ed9489887eb19786e1d8810af91267e9))
* Fix semantic release configuration ([#5](https://github.com/arxlang/arx/issues/5)) ([78ca1df](https://github.com/arxlang/arx/commit/78ca1df453df91a59b8d1d1d763c9382a4d9e958))
* Fix the documentation issues ([#3](https://github.com/arxlang/arx/issues/3)) ([9ec65a3](https://github.com/arxlang/arx/commit/9ec65a3752b3b5d6a8725bdd1a1ba95a26fc12f0))
* Fix the semantic release workflow ([#4](https://github.com/arxlang/arx/issues/4)) ([b5fb75c](https://github.com/arxlang/arx/commit/b5fb75c1f2146d455b058daee8a8f897e54eea79))
