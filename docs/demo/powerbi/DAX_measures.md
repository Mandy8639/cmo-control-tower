# Suggested DAX measures (Power BI)

Load every CSV in this folder, then relate fact tables to dim_partner[partner_id],
dim_product[material] and dim_date[date] (single direction, many-to-one).

```
OTIF % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_delivery ), fact_delivery[otif] = TRUE () ),
         COUNTROWS ( fact_delivery ) )

RFT % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_batch ), fact_batch[has_deviation] = FALSE () ),
         COUNTROWS ( fact_batch ) )

CAPA on time % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_capa ), fact_capa[on_time] = TRUE () ),
         COUNTROWS ( fact_capa ) )

Cost variance % =
DIVIDE ( SUMX ( fact_invoice, ( fact_invoice[billed_price] - fact_invoice[contract_price] ) * fact_invoice[qty_th] ),
         SUMX ( fact_invoice, fact_invoice[contract_price] * fact_invoice[qty_th] ) )

Weeks of supply (latest) =
VAR LastWeek = MAX ( fact_inventory[week_start] )
RETURN CALCULATE ( SUM ( fact_inventory[closing_th] ), fact_inventory[week_start] = LastWeek )
     / CALCULATE ( SUM ( dim_product[forecast_weekly_th] ) )
```

Suggested pages: network scorecard (matrix partner x month with OTIF/RFT/CAPA, conditional
formatting vs. dim_partner targets), partner deep dive (OTIF trend + late deliveries table),
supply outlook (weeks of supply by product with a 4-week safety-stock line), risks (fact_risk).

All operational data is synthetic; product names come from openFDA (public domain).
