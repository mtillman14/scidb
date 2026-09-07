getFactorColNames <- function(data) {
    # Return the column names of the data frame that are statistical factors
    factor_columns <- names(data)[sapply(data, is.factor)]
    return(factor_columns)
    # Get the column names of the data frame
    # colNames <- colnames(data)
    
    # # Initialize an empty vector to store factor column names
    # factorColNames <- c()
    
    # # Loop through each column name
    # for (colName in colNames) {
    #     # Loop through each row in the column from 1 to N-1
    #     isFactor <- FALSE
    #     for (i in 1:(nrow(data) - 1)) {
    #         # Check if the current row and the next row are identical
    #         if (data[i, colName] == data[i + 1, colName]) {
    #             # If they are, add the column name to the factor column names vector
    #             factorColNames <- c(factorColNames, colName)
    #             isFactor <- TRUE
    #             break  # Exit the inner loop once a duplicate is found
    #         }
    #     }
    #     if (!isFactor) {
    #         # This is the last statistical factor column
    #         factorColNames <- c(factorColNames, colName)
    #         break
    #     }
    # }
    
    # # Return the vector of factor column names
    # return(factorColNames)
}

getVariableColNames <- function(data) {
    allColNames <- colnames(data)

    factorColNames <- getFactorColNames(data)
    variableColNames <- setdiff(allColNames, factorColNames)
    return (variableColNames)
}