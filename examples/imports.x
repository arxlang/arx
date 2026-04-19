```
title: Import syntax examples
summary: Demonstrates absolute and relative import forms.
```
import toolkit.math
import toolkit.math as math

import sum from toolkit.math
import sum as add from toolkit.math

import (sum, mean as average) from toolkit.math

import sum from .math
import (sum, mean) from .stats
import helper from ..shared.helpers
