# Third-Party Notices

## STATE-Bench

The archived pilot and challenge task structures were inspired by the
following STATE-Bench tasks:

- Case 105: `105-hard_compat_dock_wrong_laptop`
- Case 121: `121-change_flight_cascade_replace_hotel`
- Case 122: `122-shortened_trip_cancel_hotel_replace_car_dates`
- Case 124: `124-cross_plan_trip_budget_with_preference_floor`

Upstream repository:
<https://github.com/microsoft/STATE-Bench>

STATE-Bench is distributed under the MIT License:

```text
MIT License

Copyright (c) 2026 STATE-Bench contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

RepairScope-Bench v0.6 imports STATE-Bench as a Git dependency fixed at commit
`4efcbf2d4fe60df04878859b692d9391f3d5b33a`. It directly instantiates the
upstream travel and customer-support environment classes and reuses their
schemas, records, policy engine, read tools, and preview/confirm write tools.
Composition-based adapters add service reservations, new purchase creation,
compatibility relations, economic contracts, failure-snapshot hashing, and
the RepairScope transaction ledger. The upstream runtime is not copied or
modified in this repository.

All v0.6 task text, inventories, prices, fixed post-failure states,
counterfactual variants, contracts, constraints, and Oracle traces are newly
generated for RepairScope-Bench. Each JSON task records the pinned upstream
commit and reuse statement.
