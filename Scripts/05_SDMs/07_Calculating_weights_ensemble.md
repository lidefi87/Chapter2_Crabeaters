Optimising weights for ensemble mean
================
Denisse Fierro Arcos
2023-12-14

- <a href="#finding-optimal-weighting-for-ensemble-mean"
  id="toc-finding-optimal-weighting-for-ensemble-mean">Finding optimal
  weighting for ensemble mean</a>
  - <a href="#loading-libraries" id="toc-loading-libraries">Loading
    libraries</a>
  - <a href="#loading-model-evaluation-metrics"
    id="toc-loading-model-evaluation-metrics">Loading model evaluation
    metrics</a>
    - <a href="#plotting-model-performance-metrics"
      id="toc-plotting-model-performance-metrics">Plotting model performance
      metrics</a>
  - <a href="#loading-testing-data" id="toc-loading-testing-data">Loading
    testing data</a>
  - <a href="#loading-models-and-getting-predictions"
    id="toc-loading-models-and-getting-predictions">Loading models and
    getting predictions</a>
  - <a href="#normalising-weights" id="toc-normalising-weights">Normalising
    weights</a>
  - <a href="#calculating-ensemble-mean-and-weighted-ensemble-mean"
    id="toc-calculating-ensemble-mean-and-weighted-ensemble-mean">Calculating
    ensemble mean and weighted ensemble mean</a>
  - <a href="#saving-weights" id="toc-saving-weights">Saving weights</a>

# Finding optimal weighting for ensemble mean

We calculated three model performance metric for each of the four models
to be included in the final ensemble mean. These metrics include: the
area under the the receiver operating curve (AUC ROC), the area under
the precision-recall gain curve (AUC PRG) and the Pearson correlation
between the model predictions and the testing dataset. AUC values give
an indication of how good the model is at discriminating presences and
absences, while the correlation gives us information about the agreement
between the observations and the model predictions.

Not all SDM algorithms performed equally well, with BRTs and RFs
outperforming GAMs and Maxent in all metrics. Therefore, the
contribution of each algorithm towards the mean distribution estimates
should be weighted by the model performance. In this notebook, we will
find the weighting scheme that produces the an ensemble mean that more
closely resembles observations (i.e., the weighted ensemble mean should
result in the smallest Root Mean Square Error or RMSE).

## Loading libraries

``` r
library(tidyverse)
library(mgcv)
library(SDMtune)
library(randomForest)
library(gbm)
source("useful_functions.R")
```

## Loading model evaluation metrics

These metrics were calculated for each SDM algorithm and compiled into a
single file.

``` r
mod_eval_path <- "../../SDM_outputs/model_evaluation.csv"
model_eval <- read_csv(mod_eval_path) 
```

    ## Rows: 12 Columns: 6
    ## ── Column specification ────────────────────────────────────────────────────────
    ## Delimiter: ","
    ## chr (2): model, env_trained
    ## dbl (4): auc_roc, auc_prg, pear_cor, pear_norm_weights
    ## 
    ## ℹ Use `spec()` to retrieve the full column specification for this data.
    ## ℹ Specify the column types or set `show_col_types = FALSE` to quiet this message.

``` r
#Check data
model_eval
```

    ## # A tibble: 12 × 6
    ##    model                  env_trained auc_roc auc_prg pear_cor pear_norm_weights
    ##    <chr>                  <chr>         <dbl>   <dbl>    <dbl>             <dbl>
    ##  1 GAM                    mod_match_…   0.633   0.403   0.104             0.0844
    ##  2 GAM                    full_access   0.677   0.557   0.142             0.116 
    ##  3 GAM                    observatio…   0.633   0.375   0.108             0.0922
    ##  4 Maxent                 mod_match_…   0.648   0.713   0.0617            0     
    ##  5 Maxent                 full_access   0.686   0.863   0.0794            0     
    ##  6 Maxent                 observatio…   0.663   0.541   0.0668            0     
    ##  7 RandomForest           mod_match_…   0.853   0.853   0.324             0.525 
    ##  8 RandomForest           full_access   0.948   0.992   0.379             0.552 
    ##  9 RandomForest           observatio…   0.918   0.972   0.317             0.560 
    ## 10 BoostedRegressionTrees mod_match_…   0.819   0.833   0.257             0.390 
    ## 11 BoostedRegressionTrees full_access   0.891   0.979   0.260             0.333 
    ## 12 BoostedRegressionTrees observatio…   0.809   0.971   0.222             0.348

### Plotting model performance metrics

Before attempting to find the best weighting scheme, we will visualise
the data.

``` r
model_eval %>% 
  #Rearrange data to facilitate plotting
  pivot_longer(c(auc_roc:pear_cor), names_to = "metric", values_to = "value") %>% 
  #Plot metrics as columns
  ggplot(aes(x = metric, y = value, fill = env_trained))+
  geom_col(position = "dodge")+
  #Divide plots by SDM algorithms and source of environmental data used for training model
  facet_grid(env_trained~model)+
  #Rotate labels for legibility
  theme(axis.text.x = element_text(angle = 90))
```

![](07_Calculating_weights_ensemble_files/figure-gfm/unnamed-chunk-3-1.png)<!-- -->

Regardless of the source of the environmental data used to train the
model, we can see the same pattern in all of them, so we will use the
smaller ACCESS-OM2-01 environmental dataset to check the best weighting
scheme.

We can also see that AUC PRG and AUC ROC also show the same pattern,
with highest values for Random Forest (RF) and smallest values for GAMs.
However, the Pearson correlation is slightly different, with the highest
values for Random Forest (RF) and smallest values for Maxent. This is
why we will use AUC PRG and the Pearson correlation to test the best
combination of weights.

## Loading testing data

``` r
#Loading data
mod_match_obs <- read_csv("../../Environmental_Data/mod-match-obs_env_pres_bg_20x_Indian_weaning.csv") %>% 
  #Setting month as factor and ordered factor
  mutate(month = as.factor(month))
```

    ## Rows: 32368 Columns: 13
    ## ── Column specification ────────────────────────────────────────────────────────
    ## Delimiter: ","
    ## dbl (13): year, month, xt_ocean, yt_ocean, presence, bottom_slope_deg, dist_...
    ## 
    ## ℹ Use `spec()` to retrieve the full column specification for this data.
    ## ℹ Specify the column types or set `show_col_types = FALSE` to quiet this message.

``` r
#Preparing training data and testing data for GAM
mod_match_obs <- prep_data(mod_match_obs, "month", split = T)

#Applying SWD format for all other algorithms
mod_data_sdm <- mod_match_obs$baked_test %>% 
  select(!year) %>% 
  sdm_format() 
```

## Loading models and getting predictions

``` r
#Loading models
#GAM
gam_mod <- readRDS("../../SDM_outputs/GAM/best_GAM_mod_match_obs.rds")
#Maxent
maxent_mod <- readRDS("../../SDM_outputs/Maxent/Mod_match_obs/reduced_Maxent_model/best_red_maxent_model.rds")
#Random Forest
rf_mod <- readRDS("../../SDM_outputs/RandomForest/Mod_match_obs/reduced_RF_mod_match_obs.rds")
#Boosted Regression Trees
brt_mod <- readRDS("../../SDM_outputs/BoostedRegressionTrees/Mod_match_obs/best_BRT_mod_match_obs.rds")

#Predictions
#GAM
gam_pred <- predict(gam_mod, mod_match_obs$baked_test, type = "response")
#Maxent
maxent_pred <- predict(maxent_mod, mod_data_sdm@data, type = "cloglog")
#Random Forest
rf_pred <- predict(rf_mod, mod_data_sdm@data, type = "response")
#Boosted Regression Trees
brt_pred <- predict(brt_mod, mod_data_sdm@data, type = "response")

#Getting all predictions into a single tibble
preds <- tibble(gam = as.numeric(gam_pred), maxent = maxent_pred, rf = rf_pred, brt = brt_pred) 
```

## Normalising weights

``` r
#Getting relevant weights
weights <- model_eval %>% 
  filter(env_trained == "mod_match_obs")

#Normalising weights
weights <- weights %>% 
  ungroup() %>%
  mutate(auc_norm_weights = (auc_prg - min(auc_prg))/(max(auc_prg)-min(auc_prg)),
         pear_norm_weights = (pear_cor - min(pear_cor))/(max(pear_cor)-min(pear_cor))) %>% 
  #Ensuring values add up to 1
  mutate(auc_norm_weights = auc_norm_weights/sum(auc_norm_weights),
         pear_norm_weights = pear_norm_weights/sum(pear_norm_weights))
```

## Calculating ensemble mean and weighted ensemble mean

We will calculate the RMSE value for the unweighted ensemble mean and
weighted ensemble means. We will also use two types of weights: raw and
normalised AUC PRG and Pearson correlation values.

``` r
preds <- preds %>% 
  rowwise() %>%
  #Calculating ensemble mean (unweighted)
  mutate(ensemble_mean =  mean(c_across(gam:brt)),
         #Weighted ensemble means
         auc_weighted_ensemble_mean = weighted.mean(c_across(gam:brt), w = weights$auc_prg),
         auc_norm_weighted_ensemble_mean = weighted.mean(c_across(gam:brt), w = weights$auc_norm_weights),
         pear_weighted_ensemble_mean = weighted.mean(c_across(gam:brt), w = weights$pear_cor),
         pear_norm_weighted_ensemble_mean = weighted.mean(c_across(gam:brt), w = weights$pear_norm_weights))

#Checking results
head(preds)
```

    ## # A tibble: 6 × 9
    ## # Rowwise: 
    ##     gam maxent    rf    brt ensemble_mean auc_weighted_ensemble_mean
    ##   <dbl>  <dbl> <dbl>  <dbl>         <dbl>                      <dbl>
    ## 1 0.403  1     0.668 0.890          0.740                      0.780
    ## 2 0.322  0.567 0.654 0.857          0.600                      0.645
    ## 3 0.476  0.628 0.695 0.883          0.671                      0.702
    ## 4 0.472  0.726 0.735 0.912          0.711                      0.747
    ## 5 0.401  0.390 0.675 0.821          0.572                      0.607
    ## 6 0.471  0.589 0.170 0.0221         0.313                      0.276
    ## # ℹ 3 more variables: auc_norm_weighted_ensemble_mean <dbl>,
    ## #   pear_weighted_ensemble_mean <dbl>, pear_norm_weighted_ensemble_mean <dbl>

``` r
#Calculating RMSE values
preds %>% 
  ungroup() %>% 
  #Apply to all ensemble mean columns (weighted and unweighted)
  summarise(across(ensemble_mean:pear_norm_weighted_ensemble_mean,
                ~ sqrt(mean((mod_match_obs$baked_test$presence - .x)^2)))) %>% 
  #Reorganise table to ease interpretation
  pivot_longer(everything(), names_to = "weight_type", values_to = "RMSE") %>% 
  #Arrange by RMSE values
  arrange(RMSE)
```

    ## # A tibble: 5 × 2
    ##   weight_type                       RMSE
    ##   <chr>                            <dbl>
    ## 1 pear_norm_weighted_ensemble_mean 0.162
    ## 2 pear_weighted_ensemble_mean      0.194
    ## 3 auc_norm_weighted_ensemble_mean  0.216
    ## 4 auc_weighted_ensemble_mean       0.262
    ## 5 ensemble_mean                    0.300

The smallest RMSE was estimated when normalised Pearson correlation
values were applied as weights. We will use these weights in the final
ensemble mean. We will now calculate the normalised Pearson values and
save the weights so we can easily apply them to the final result.

## Saving weights

``` r
model_eval %>% 
  group_by(env_trained) %>% 
  #Normalising
  mutate(pear_norm_weights = (pear_cor - min(pear_cor))/(max(pear_cor)-min(pear_cor))) %>% 
  #Ensuring values add up to 1
  mutate(pear_norm_weights = pear_norm_weights/sum(pear_norm_weights)) %>% 
  #Saving results
  write_csv(mod_eval_path)
```