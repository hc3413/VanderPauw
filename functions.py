#import all the libraries needed
from import_dep import *


def import_ppms_data(path):
    '''
    This function imports the data from the PPMS instrument.
    '''
    # Import the data
    # Import the file, treating lines with non-numeric data as comments
    ppms_df = pd.read_csv(path, sep='\t', skiprows=6, header=None, comment='N')

    # Drop unwanted columns
    ppms_df.drop(ppms_df.columns[[6, 7]], axis=1, inplace=True)

    # Assign headers to columns
    ppms_df.columns = ['Temp', 'Field', 'Source (A)', 'Source (V)', 'Sense (V)', 'index']

    # Convert columns to the appropriate data types
    ppms_df['Temp'] = pd.to_numeric(ppms_df['Temp'], errors='coerce')
    ppms_df['Field'] = pd.to_numeric(ppms_df['Field'], errors='coerce')
    ppms_df['Source (A)'] = pd.to_numeric(ppms_df['Source (A)'], errors='coerce')
    ppms_df['Source (V)'] = pd.to_numeric(ppms_df['Source (V)'], errors='coerce')
    ppms_df['Sense (V)'] = pd.to_numeric(ppms_df['Sense (V)'], errors='coerce')
    ppms_df['index'] = pd.to_numeric(ppms_df['index'], downcast='integer', errors='coerce')

    # Drop rows where all values are NaN (e.g., empty lines)
    ppms_df.dropna(how='all', inplace=True)

    # Convert the 'index' column to integer format
    ppms_df['index'] = ppms_df['index'].astype(int)

    # Convert the data frame to a numpy array
    ndnp = ppms_df.to_numpy()

    # Slice the array taking every 6th value (i.e the different index values) 
    # then stack these 2d arrays to generate a 3d array
    # The new array has (rows, columns, index) dimensions
    ppms_np = np.array([ndnp[q::6,:-1] for q in range(6)])
    ppms_np = ppms_np.transpose(1,2,0)
    return ppms_np, ppms_df


def extract_ctf(data_np):
    '''extract the number of temperature, field and current points used in the measurements
    Also extract the rounded values of the temperature, field and current used in the measurements
    These rounded values can be displayed to check they are as expected where the true more accurate values are used for the calculations
    tf_av are the true, meausured average temperature and field values used for each set of current measurements'''
    
    #### Step 1: Extract the rounded Current, Temperature, and Field values used from the data
    
    # Find the rounded values of current used and the number of unique current points
    current_round = np.round(data_np[:,2,0],decimals=7)
    current_unique = np.unique(current_round)
    current_no = current_unique.shape[0]
    
    # Find the rounded values of temperature used and the number of unique temperature points
    temp_round = np.round(data_np[:,0,0],decimals=0)
    temp_unique = np.unique(temp_round)
    temp_no = temp_unique.shape[0]
    
    # Find the rounded values of field used and the number of unique field points
    # Can't use the np.unique for field as there are repeats of 0 field so it would miscount the field points used per loop
    field_no = int(data_np.shape[0]/temp_no/current_no)
    field_unique = data_np[0:current_no*field_no:current_no,1,0]
    
    # Store the current, temperature and field data in an array to output from the funtion for later use
    ctf = [current_unique, temp_unique, field_unique, current_no, temp_no, field_no]
    
    
    
    #### Step 2: Extract the true temperature and field values averaged over all the index values

    #initialize empty array to store the temp and field values averaged over each set of currents and each index value
    tf_av = np.zeros((ctf[4]*ctf[5],2,6))
    
    # slice the data for each current point and sum them, dividing by the total number to get the field and temperature averaged over all the currents
    for i in range(current_no):
                tf_av += data_np[i::current_no,:2,:]/current_no
    #sum over all the index values and divide by the number of indexes to get average temp and fields for each full set of electrical measurements (index 0-6)
    tf_av = np.sum(tf_av, axis=2)/np.shape(data_np)[2]
    
    return ctf, tf_av



def vdp_equation(rho_sheet, R_A, R_B):
    '''Solves the Van der Pauw equation for the sheet resistivity of a thin film sample.'''
    return np.exp(-np.pi * R_A / rho_sheet) + np.exp(-np.pi * R_B / rho_sheet) - 1


def vdp_resistivity(data_np, film_thickness,ctf,tf_av):
    '''Calculates the resistivity of a thin film sample using the Van der Pauw method.
    The measurments for this were done in index values of 2,3,4,5 
    Each index value corresponds to a different configuration of the source and sense leads.
    These 4 index configurations are split into 2 pairs of configurations, with each pair being able to generate the resistivity of the film independantly.
    Four configurations were used for robustness, to enable a comparison of the resistivity values obtained with the source/sense positions swapped.'''
  
    # Initialise a list to store the R^2 value for the IV data and check we have a good fit for the linear regression
    R_squared = []
    
    # Find the number of measurement points at which the currents were measured (i.e each set of temperature and field values)
    points_per_index = ctf[4]*ctf[5]
    
    # Initialize an empty np aray to store each temperature, field, and the resitivities for: config A, config B, average of A and B
    res_data = np.zeros((points_per_index, 5))

    #Loop over each temperature and field combination, calculating the sheet resistivity using the Van der Pauw method
    for i in range(points_per_index):
        
        # Generate a variable to increment by the number of current points measured for each interation of the loop
        # thus going to the next measured set of currents each loop
        increment = i*ctf[3]
        
        ##### Using linear regression on the current-voltage data to obtain: 
        ### R_ij_kl[0] = the slope(resistance), R_ij_kl[1] = intercept, R_ij_kl[2] = R-squared value

        #First pair of Van der Pauw configurations
        R_32_10 = linregress(data_np[increment:ctf[3]+increment,2,2], data_np[increment:ctf[3]+increment,4,2])    
        R_20_31 = linregress(data_np[increment:ctf[3]+increment,2,3], data_np[increment:ctf[3]+increment,4,3])
        #Second pair of Van der Pauw configurations
        R_01_23 = linregress(data_np[increment:ctf[3]+increment,2,4], data_np[increment:ctf[3]+increment,4,4])
        R_13_02 = linregress(data_np[increment:ctf[3]+increment,2,5], data_np[increment:ctf[3]+increment,4,5])

        # Append the R-squared value to the list
        R_squared.extend([R_32_10[2], R_20_31[2], R_01_23[2], R_13_02[2]])

        ##### Solve the Van der Pauw equation for both pairs of configurations

        # Initial guess for rho_sheet
        initial_guess = 1.0

        # Solve for rho_sheet for the first pair (R_A)
        R_sheet_A = fsolve(vdp_equation, initial_guess, args=(R_32_10[0], R_20_31[0]))[0]

        # Solve for rho_sheet for the second pair (R_B)
        R_sheet_B = fsolve(vdp_equation, initial_guess, args=(R_01_23[0], R_13_02[0]))[0]

        # Average the two solutions for the final sheet resistivity
        R_sheet = (R_sheet_A + R_sheet_B) / 2
        
        # Step 3: Insert the new row to the np data array
        res_data[i,:] = [tf_av[i,0], tf_av[i,1], R_sheet_A*film_thickness, R_sheet_B*film_thickness,R_sheet*film_thickness]
    
    # Convert the numpy array to a pandas dataframe then return the data in both forms along with the R-squared values
    df_res_data = pd.DataFrame(res_data, columns=['Temp', 'Field', 'rho_xx_A', 'rho_xx_B','rho_xx_average'])
    return res_data, df_res_data, R_squared



def magnetoresistance(data_np, film_thickness,ctf,tf_av):
    '''Calculates the magnetoresistance of a thin film sample using the Van der Pauw method.
    Outputs the magnetoresistance values for each temperature and field strength.
    Third index stores the magnetoresistance value for rho_A, rho_B, and the average of the two: rho_film to look at any ayssmetries with direction'''
    # Calculate the resistivity of the thin film sample using the Van der Pauw method
    [res_data, _, _] = vdp_resistivity(data_np, film_thickness, ctf, tf_av)
    
    # Initialize an empty array to store the magnetoresistance data at each temperature (rows) and field strength (columns)
    # The third index stores the magnetoresistance value for rho_A, rho_B, and the average of the two: rho_film to look at any ayssmetries with direction
    mag_res = np.zeros((ctf[4], ctf[5],3))
    
    # Loop over the temperature and field data extracting the magnetoresistance values
    for t_count, t in enumerate(ctf[1], start=0):
        for f_count, f in enumerate(ctf[2], start=0):
            # Magnetoresistance = 100*(R(H) - R(0)) / R(0)
            mag_res[t_count,f_count,:] = 100*(res_data[int(t_count*ctf[5]+f_count),2:5]-res_data[int(t_count*ctf[5]),2:5])/res_data[int(t_count*ctf[5]),2:5]
            #print(f'For T={t} K and B={f} Oe, magnetoresistance = {mag_res[t_count,f_count]} %')
        
    return mag_res



def vdp_hall(data_np, film_thickness,ctf,tf_av):
    '''Calculates the Hall resistivity at every temperature and field strength
    Uses linear regression on the current-voltage data to obtain the Hall resistivity
    The Hall resistivity is calculated for each configuration of the source and sense leads and the two are averaged
    Though caution is needed on this average as the Hall resistivity is a vector quantity and the two configurations may not be identical
    (rho_xy = thickness*V(hall)/I(source))'''
    #ctf = [current_unique, temp_unique, field_unique, current_no, temp_no, field_no]
    
    # Initialise a list to store the R^2 value for the IV data and check we have a good fit for the linear regression
    R_squared = []
    
    # Find the number of measurement points at which the currents were measured (i.e each set of temperature and field values)
    points_per_index = ctf[4]*ctf[5]
    
    # Initialize an empty np aray to store the temperature, field, hall resistance: in config A, config B and Average 
    hall_data = np.zeros((points_per_index, 5))

    #Loop over each temperature and field combination, calculating the hall resistance (Vperp/I)
    for i in range(points_per_index):
        
        # Generate a variable to increment by the number of current points measured for each interation of the loop
        # thus going to the next measured set of currents each loop
        increment = i*ctf[3]
        
        ##### Using linear regression on the current-voltage data to obtain: 
        ### R_ij_kl[0] = the slope(resistance), R_ij_kl[1] = intercept, R_ij_kl[2] = R-squared value

        #Hall Configuration A
        R_13_42 = linregress(data_np[increment:ctf[3]+increment,2,0], data_np[increment:ctf[3]+increment,4,0])[0]    
        #Hall Configuration B (with source and sense leads swapped)
        R_24_31 = linregress(data_np[increment:ctf[3]+increment,2,0], data_np[increment:ctf[3]+increment,4,0])[0]

        # Average the two solutions for the final sheet resistivity
        R_hall_average = (R_13_42 + R_24_31) / 2
        
        # Step 3: Insert the new row to the np data array
        hall_data[i,:] = [tf_av[i,0], tf_av[i,1], R_13_42*film_thickness, R_24_31*film_thickness,R_hall_average*film_thickness]
    
    # Convert the numpy array to a pandas dataframe then return the data in both forms along with the R-squared values
    df_hall_data = pd.DataFrame(hall_data, columns=['Temp', 'Field', 'rho_xy_A', 'rho_xy_B','rho_xy_average'])
    return hall_data, df_hall_data, R_squared



