library(shiny)
library(plotly)
library(shinyjs)
library(DT)
library(dplyr)
library(ggplot2)
library(svglite)

source("getColNames.R")

server <- function(input, output, session) {

  #########################################################
  # INITIALIZE REACTIVE VALUES
  #########################################################

  # Initialize reactive values to store the original and modified data frame
  data_store_original <- reactiveVal(NULL)
  data_store <- reactiveVal(NULL)

  # Initialize reactive value to store the full list of factors.
  factor_list_original <- reactiveVal(NULL)
  
  # Initialize the color factor
  color_factor <- reactiveVal(NULL)
  
  # Initialize the facet factor
  facet_factor <- reactiveVal(NULL)

  # Initialize the Plotly plot
  plotly_plot <- reactiveVal(NULL)
  ggplot_plot <- reactiveVal(NULL)

  # Initialize the column name being plotted
  col_name <- reactiveVal(NULL)

  #########################################################
  # LOAD CSV
  #########################################################

  observeEvent(input$browseFileButton, {
    # Code to handle file browsing and loading
    showModal(modalDialog(
      title = "File Browser",
      fileInput("fileInput", "Choose CSV File", accept = ".csv"),
      footer = tagList(
        modalButton("Cancel"),
        actionButton("loadFile", "Load File")
      )
    ))
  })

  observeEvent(input$loadFile, {
    req(input$fileInput)
    data <- read.csv(input$fileInput$datapath, stringsAsFactors = TRUE)    

    output$filePath <- renderText({
      paste("Loaded file name:", input$fileInput$name)
    })

    removeModal()

    factorColNames <- getFactorColNames(data)
    variableColNames <- getVariableColNames(data)

    # Store the full list of factors in a reactive value
    factor_list_original(factorColNames)

    # Make sure each of the factorColNames are factors in the data data frame
    for (col in factorColNames) {
        data[[col]] <- as.factor(data[[col]])
    }

    if (length(factorColNames) > 2) {
        defaultSelectedFactor <- factorColNames[2]
    } else {
        defaultSelectedFactor <- factorColNames[1]
    }

    updateSelectInput(session, "outcomeMeasureDropDown",
                      label = "Variable to Plot",
                      choices = variableColNames)

    updateCheckboxGroupInput(session, "dataReductionFactorsCheckboxGroup",
                             label = "Average Over Factors",
                             choices = factorColNames)

    updateCheckboxGroupInput(session, "plotReplicateCheckboxGroup",
                             label = "Plot Replication Factors",
                             choices = factorColNames)

    updateSelectInput(session, "tickFactorsselectInput",
                         label = "XTick Factor Order",
                         choices = factorColNames,
                         selected = defaultSelectedFactor)  # Set the first one or two factor columns to be selected by default
    
    updateSelectInput(session, "colorFactorSelectInput",
                        label = "Color Factor",
                        choices = factorColNames)
    
    updateCheckboxGroupInput(session, "facetFactorCheckboxGroup",
                        label = "Facet Factor",
                        choices = factorColNames)

    output$dataTable <- renderDT({
        datatable(data)
    })

    # Store the data in a reactive value
    data_store_original(data)
    data_store(data)
  })

  #########################################################
  # CHANGE VARIABLE
  #########################################################
  observeEvent(input$outcomeMeasureDropDown, {
    selectedOutcomeMeasure <- input$outcomeMeasureDropDown

    # Update the column name being plotted
    col_name(selectedOutcomeMeasure)
  })

  #########################################################
  # SHOW/HIDE SIDEBAR
  #########################################################
  observeEvent(input$exportButton, {
    req(plotly_plot())
    req(col_name())

    # Get the column name being plotted
    colName <- col_name()
    
    # Create better filenames with the column name
    timestamp <- format(Sys.time(), "%Y%m%d-%H%M%S")
    png_filename <- paste0(colName, "_", timestamp, ".png")
    svg_filename <- paste0(colName, "_", timestamp, ".svg")
    
    # Create temporary files with proper names
    temp_png <- file.path(tempdir(), png_filename)
    temp_svg <- file.path(tempdir(), svg_filename)

    # Use the ggplot object for saving
    p <- ggplot_plot()

    # Save the files with proper names
    ggsave(temp_png, plot = p, device = "png", width = 8, height = 6)
    ggsave(temp_svg, plot = p, device = "svg", width = 8, height = 6)

    # Show a modal dialog with buttons for each format
    showModal(modalDialog(
        title = "Download Plot",
        "Choose a format to download your plot:",
        footer = tagList(
            downloadButton("downloadPNG", "Download PNG"),
            downloadButton("downloadSVG", "Download SVG")
        ),
        easyClose = TRUE
    ))
    
    # Define download handlers for each format
    output$downloadPNG <- downloadHandler(
        filename = function() {
            png_filename  # Use the filename with colName already included
        },
        content = function(file) {
            file.copy(temp_png, file)
        },
        contentType = "image/png"
    )
    
    output$downloadSVG <- downloadHandler(
        filename = function() {
            svg_filename  # Use the filename with colName already included
        },
        content = function(file) {
            file.copy(temp_svg, file)
        },
        contentType = "image/svg+xml"
    )
  })
  
  observeEvent(input$settingsButton, {
    # Code to handle settings functionality
    showModal(modalDialog(
      title = "Settings",
      "Settings functionality is not implemented yet.",
      easyClose = TRUE,
      footer = NULL
    ))
  })  

  #########################################################
  # SIDEBAR: GROUPING SETTINGS
  #########################################################
  observeEvent(input$dataReductionFactorsCheckboxGroup, {
    req(data_store_original())
    data <- data_store_original()

    # Get the selected factors from the checkbox group
    selectedFactors <- input$dataReductionFactorsCheckboxGroup

    variableColNames <- getVariableColNames(data)
    factorColNames <- getFactorColNames(data)
    unselectedFactors <- setdiff(factorColNames, selectedFactors)

    if (length(selectedFactors) == 0) {
        averagedData <- data
        xtickFactors <- factorColNames
        plotReplicationFactors <- factorColNames
        colorFactors <- factorColNames
        facetFactors <- factorColNames
    } else {
        xtickFactors <- unselectedFactors
        plotReplicationFactors <- unselectedFactors
        colorFactors <- unselectedFactors
        facetFactors <- unselectedFactors
        # Average the data by the selected factors
        averagedData <- data %>%
        group_by(across(all_of(unselectedFactors))) %>%
        summarise(across(where(is.numeric), mean, na.rm = TRUE), .groups = "drop") %>%
        select(-one_of(selectedFactors))  # Remove the selected factors from the data frame
    }

    # Update the Plot Replication Factors checkbox group
    updateCheckboxGroupInput(session, "plotReplicateCheckboxGroup",
                             label = "Plot Replication Factors",
                             choices = plotReplicationFactors)

    # Update the XTick Factor Order selectize input
    updateSelectInput(session, "tickFactorsselectInput",
                         label = "XTick Factor Order",
                         choices = xtickFactors)
    
    # Update the Color Factor select input
    updateSelectInput(session, "colorFactorSelectInput",
                        label = "Color Factor",
                        choices = colorFactors)
    
    # Update the Facet Factor select input
    updateCheckboxGroupInput(session, "facetFactorCheckboxGroup",
                        label = "Facet Factor",
                        choices = facetFactors)

    # Update the data table with the averaged data
    output$dataTable <- renderDT({
    datatable(averagedData)
    })

    # Update the data store with the averaged data
    data_store(averagedData)
  }, ignoreNULL = FALSE)

  observeEvent(input$tickFactorsselectInput, {
    dataReductionFactors <- factor_list_original()
    selectedDataReductionFactors <- input$dataReductionFactorsCheckboxGroup

    unselectedDataReductionFactors <- setdiff(dataReductionFactors, selectedDataReductionFactors)

    selectedXTickFactors <- input$tickFactorsselectInput    

    # Plot replication factors are the unselected data reduction factors, and the unselected XTicks
    plotReplicationFactors <- setdiff(unselectedDataReductionFactors, selectedXTickFactors)

    updateCheckboxGroupInput(session, "plotReplicateCheckboxGroup",
                             label = "Plot Replication Factors",
                             choices = plotReplicationFactors)
  })
  
  observeEvent(input$colorFactorSelectInput, {
    colorFactor <- input$colorFactorSelectInput
    
    if (length(colorFactor) == 0 || colorFactor == "") {
      colorFactor <- NULL
    }
    
    color_factor(colorFactor)
  })
  
  observeEvent(input$facetFactorCheckboxGroup, {
    facetFactor <- input$facetFactorCheckboxGroup
    
    if (length(facetFactor) == 0 || facetFactor == "") {
      facetFactor <- NULL
    }
    
    facet_factor(facetFactor)
  })

  #########################################################
  # SIDEBAR: EXPORT SETTINGS
  #########################################################  

  #########################################################
  # SIDEBAR: RUN PLOT
  #########################################################
  observeEvent(input$runPlotButton, {
    data <- data_store()
    colorFactor <- color_factor()
    facetFactor <- facet_factor()
    factorColNames <- names(data)[sapply(data, is.factor)]
    selectedOutcomeMeasure <- input$outcomeMeasureDropDown
    # Remove all of the variable columns from the data frame except for the selected outcome measure
    selectedDataReductionFactors <- input$dataReductionFactorsCheckboxGroup
    selectedXTickFactors <- input$tickFactorsselectInput

    # Add defaultFactor column
    data$Observation <- 1:nrow(data)
    if (length(selectedXTickFactors) == 0 || length(selectedXTickFactors) == length(factorColNames)) {
        selectedXTickFactors <- c("Observation")
    }
    
    # Define the factors in the tooltip
    factors_for_tooltip <- setdiff(factorColNames, selectedXTickFactors)
    
    # Create tooltip text dynamically
    tooltip_parts <- c(
      "paste('Value: ', round(!!sym(selectedOutcomeMeasure), 4)"
    )
    
    for (factor in factors_for_tooltip) {
      tooltip_parts <- c(tooltip_parts, 
                         paste0("'<br>", factor, ": ', ", factor))
    }
    
    tooltip_expr <- paste(tooltip_parts, collapse = ", ")
    tooltip_expr <- paste0(tooltip_expr, ")")
    
    # Parse and evaluate the expression
    tooltip_aes <- eval(parse(text = paste0("aes(text = ", tooltip_expr, ")")))

    # Create a formula for the x-axis using the selected XTick factors
    xFormula <- as.formula(paste0("~", paste(selectedXTickFactors, collapse = " + ")))
    yFormula <- as.formula(paste0("~", selectedOutcomeMeasure))
    
    # Plot differently depending on how many X tick factors are selected.
    # if (length(selectedXTickFactors) > 2) {
    #   showModal(modalDialog(
    #     title = "Unsupported Selection",
    #     "Too many X Tick factors selected Only 1 or 2 are supported!",
    #     easyClose = TRUE,
    #     footer = modalButton("Close")
    #   ))
    #   return()
    # }
    
    # if (length(selectedXTickFactors) == 2) {
    #   tickFactor = selectedXTickFactors[1]
    #   facetFactor = selectedXTickFactors[2]
    # }
    
    if (length(selectedXTickFactors) == 1) {
      tickFactor = selectedXTickFactors[1]
      
      p <- ggplot(data, aes(x = !!sym(tickFactor), y = !!sym(selectedOutcomeMeasure))) +
        geom_point(position = position_dodge(width = 0.6), size = 3, alpha = 0.8) +
        scale_x_discrete(name = tickFactor)
      
      # Add the tooltip mapping to the plot
      p <- p + tooltip_aes
    }
    
    if (!is.null(colorFactor)) {
      p <- p + aes(color = !!sym(colorFactor))
    }    
    
    if (!is.null(facetFactor)) {
        if (!is.vector(facetFactor)) {
            facetFactor <- c(facetFactor)
        }
      p <- p + facet_wrap(vars(!!!syms(facetFactor)))
    }
    
    # Convert to plotly for interactivity
    p_interactive <- ggplotly(p, tooltip = "text", mode = "markers")
    
    output$plot <- renderPlotly({p_interactive})

    plotly_plot(p_interactive)
    ggplot_plot(p)
  })
}