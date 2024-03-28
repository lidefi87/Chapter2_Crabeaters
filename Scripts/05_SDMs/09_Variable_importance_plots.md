Variable importance plots
================
Denisse Fierro Arcos
2024-03-28

- <a href="#variable-importance-by-species-distribution-model-sdms"
  id="toc-variable-importance-by-species-distribution-model-sdms">Variable
  importance by Species Distribution Model (SDMs)</a>
  - <a href="#loading-libraries" id="toc-loading-libraries">Loading
    libraries</a>
  - <a href="#loading-ggplot2-objects"
    id="toc-loading-ggplot2-objects">Loading <code>ggplot2</code>
    objects</a>
  - <a href="#bar-plot-for-models-trained-with-access-om2-01-full-set"
    id="toc-bar-plot-for-models-trained-with-access-om2-01-full-set">Bar
    plot for models trained with ACCESS-OM2-01 full set</a>
  - <a href="#bar-plot-for-models-trained-with-access-om2-01-reduced-set"
    id="toc-bar-plot-for-models-trained-with-access-om2-01-reduced-set">Bar
    plot for models trained with ACCESS-OM2-01 reduced set</a>
  - <a href="#bar-plot-for-models-trained-with-observations"
    id="toc-bar-plot-for-models-trained-with-observations">Bar plot for
    models trained with observations</a>

# Variable importance by Species Distribution Model (SDMs)

We use variable importance plots produced by the modelling scripts
included in this folder. We will combine them into a single figure for
each environmental dataset.

## Loading libraries

``` r
library(tidyverse)
library(cowplot)
```

## Loading `ggplot2` objects

``` r
ggobj_list <- list.files("../../SDM_outputs/", pattern = ".rds$", 
                         full.names = T)
```

## Bar plot for models trained with ACCESS-OM2-01 full set

``` r
var_imp_plot <- function(ggobj, mod_name, lims){
  #Access data used in plot
  p <- ggobj$data %>% 
    #arrange by variable importance
    arrange(desc(Permutation_importance)) %>% 
    rowid_to_column("id") %>% 
    #calculate cumulative sum for importance contribution
    mutate(cum_sum = cumsum(Permutation_importance),
           #blue colours if cum sum up to 60%
           fill = case_when((cum_sum <= 0.6 | id == 1) ~ "#004488",
                            T ~ "#bbbbbb")) %>% 
    #Initialise plot
    ggplot(aes(y = Variable, x = Permutation_importance, fill = fill))+
    #Column plot
    geom_col()+
    #use values in fill column as colours
    scale_fill_identity()+
    #Apply b&W theme
    theme_bw()+
    #Change labels
    labs(x = "Permutation importance", title = mod_name)+
    theme(axis.title.y = element_blank(), 
          plot.title = element_text(hjust = 0.5))+
    #Scales to be applied based on maximum values seen in plots
    scale_x_continuous(limits = lims, labels = scales::label_percent())
}
```

``` r
#Get list of files for ACCESS-OM2-01 full set
mod_full <- ggobj_list %>% 
  str_subset(".*mod_full.rds")

#Create empty list to store plots
mod_full_plots <- list()

#Loop through each element of the list
for(i in seq_along(mod_full)){
  #Get model name from file name
  model <- str_remove(basename(mod_full[i]), "_var.*")
  #Load ggplot2 object
  ggobj <- readRDS(mod_full[i])
  p <- var_imp_plot(ggobj, model, c(0, .30))
  #If first two plots, then make x axis title bank
  if(i < 3){
    p <- p+
      labs(x = "")
  }
  #Save plots into list
  mod_full_plots[[model]] <- p
}

#Turn into a single plot
mod_full_plots <- plot_grid(plotlist = mod_full_plots, nrow = 2, 
                            labels = c("A", "B", "C", "D"))

ggsave("../../SDM_outputs/var_imp_mod_full.png", mod_full_plots, 
       device = "png", width = 9)
```

    ## Saving 9 x 5 in image

## Bar plot for models trained with ACCESS-OM2-01 reduced set

``` r
#Get list of files for ACCESS-OM2-01 full set
mod_match_obs <- ggobj_list %>% 
  str_subset(".*mod_match_obs.rds")

#Create empty list to store plots
mod_match_obs_plots <- list()

#Loop through each element of the list
for(i in seq_along(mod_match_obs)){
  #Get model name from file name
  model <- str_remove(basename(mod_match_obs[i]), "_var.*")
  #Load ggplot2 object
  ggobj <- readRDS(mod_match_obs[i])
  #Create plot
  p <- var_imp_plot(ggobj, model, c(0, .45))
  
  #If first two plots, then make x axis title bank
  if(i < 3){
    p <- p+
      labs(x = "")
  }
  #Save plots into list
  mod_match_obs_plots[[model]] <- p
}

#Turn into a single plot
mod_match_obs_plots <- plot_grid(plotlist = mod_match_obs_plots, nrow = 2, 
                            labels = c("A", "B", "C", "D"))

ggsave("../../SDM_outputs/var_imp_mod_match_obs.png", mod_match_obs_plots, 
       device = "png", width = 9)
```

    ## Saving 9 x 5 in image

## Bar plot for models trained with observations

``` r
#Get list of files for ACCESS-OM2-01 full set
obs <- ggobj_list %>% 
  str_subset(".*imp_obs.rds")

#Create empty list to store plots
obs_plots <- list()

#Loop through each element of the list
for(i in seq_along(obs)){
  #Get model name from file name
  model <- str_remove(basename(obs[i]), "_var.*")
  #Load ggplot2 object
  ggobj <- readRDS(obs[i])
  #Create plot
  p <- var_imp_plot(ggobj, model, c(0, .65))
  
  #If first two plots, then make x axis title bank
  if(i < 3){
    p <- p+
      labs(x = "")
  }
  #Save plots into list
  obs_plots[[model]] <- p
}

#Turn into a single plot
obs_plots <- plot_grid(plotlist = obs_plots, nrow = 2, 
                       labels = c("A", "B", "C", "D"))

ggsave("../../SDM_outputs/var_imp_obs.png", obs_plots, 
       device = "png", width = 9)
```

    ## Saving 9 x 5 in image